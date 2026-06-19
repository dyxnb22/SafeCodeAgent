"""Console evidence, eval, and cost read-only offline tests (v2.3.4-T1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
CONSOLE_ROOT = ROOT / "console"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "persistence"))
from backend_contract import sample_checkpoint  # noqa: E402

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.trace.events import TraceEventType

_BASELINES_ROOT = ROOT / "tests" / "enterprise" / "eval" / "baselines"


def _client(tmp_path: Path) -> tuple[TestClient, LocalBackend]:
    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:dev"}
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev",
            tenant_id="tenant-a",
            roles=(Role.developer,),
        ),
        eval_baselines_root=_BASELINES_ROOT,
    )
    return TestClient(app), backend


def test_console_evidence_eval_source_files_exist() -> None:
    required = (
        "src/lib/api/evidence.ts",
        "src/lib/api/eval.ts",
        "src/components/cost/CostSummary.tsx",
        "src/app/t/[tenantId]/runs/[runId]/evidence/page.tsx",
        "src/app/t/[tenantId]/eval/page.tsx",
    )
    for relative in required:
        assert (CONSOLE_ROOT / relative).is_file(), relative


def test_evidence_page_is_read_only_export() -> None:
    evidence_page = (CONSOLE_ROOT / "src/app/t/[tenantId]/runs/[runId]/evidence/page.tsx").read_text(
        encoding="utf-8"
    )
    assert "downloadEvidence" in evidence_page
    assert "Download evidence bundle" in evidence_page


def test_eval_page_lists_baselines_read_only(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    response = client.get("/v2/eval/baselines", params={"tenant_id": "tenant-a"})
    assert response.status_code == 200
    suites = {item["suite"] for item in response.json()["items"]}
    assert "retrieval" in suites


def test_evidence_export_returns_zip(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-evidence001"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    backend.trace.emit_event(
        tenant_id="tenant-a",
        run_id=run_id,
        event_type=TraceEventType.node_start,
        node_id="classify_request",
        seq=1,
    )

    response = client.get(f"/v2/evidence/{run_id}", params={"tenant_id": "tenant-a"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.content.startswith(b"PK")
