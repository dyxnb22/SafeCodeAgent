"""Console approval inbox offline tests (v2.3.3-T1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
CONSOLE_ROOT = ROOT / "console"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "persistence"))
from backend_contract import sample_checkpoint, sample_request  # noqa: E402

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role


def _client(tmp_path: Path) -> tuple[TestClient, LocalBackend]:
    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:reviewer"}
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:reviewer",
            tenant_id="tenant-a",
            roles=(Role.maintainer,),
        ),
    )
    return TestClient(app), backend


def test_console_approval_source_files_exist() -> None:
    required = (
        "src/lib/api/approvals.ts",
        "src/components/approvals/ApprovalList.tsx",
        "src/components/approvals/ApprovalDecideForm.tsx",
        "src/app/t/[tenantId]/approvals/page.tsx",
    )
    for relative in required:
        assert (CONSOLE_ROOT / relative).is_file(), relative


def test_approval_decide_client_uses_idempotency_key_only_for_writes() -> None:
    module = (CONSOLE_ROOT / "src/lib/api/approvals.ts").read_text(encoding="utf-8")
    assert "Idempotency-Key" in (CONSOLE_ROOT / "src/lib/api/client.ts").read_text(encoding="utf-8")
    assert "idempotencyKey" in module
    assert "decide" in module


def test_approval_decide_endpoint_records_decision(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-approval001"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    pending = sample_request(run_id=run_id, request_id="approval-console01", tenant_id="tenant-a")
    backend.approvals.save_request(tenant_id="tenant-a", request=pending)

    response = client.post(
        "/v2/approvals/approval-console01/decide",
        headers={
            "X-Tenant-Id": "tenant-a",
            "Idempotency-Key": "console-decide-key01",
        },
        json={"decision": "approved", "rationale": "console review"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_id"] == "approval-console01"
    assert body["status"] == "approved"


def test_approval_decide_requires_idempotency_key(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-approval002"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    pending = sample_request(run_id=run_id, request_id="approval-console02", tenant_id="tenant-a")
    backend.approvals.save_request(tenant_id="tenant-a", request=pending)

    response = client.post(
        "/v2/approvals/approval-console02/decide",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"decision": "rejected", "rationale": "missing key"},
    )
    assert response.status_code == 400
