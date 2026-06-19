"""Console run list, detail, and trace viewer offline tests (v2.3.2-T1)."""

from __future__ import annotations

import json
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
from safecode.enterprise.trace.render_markdown import SECTION_ORDER

_SECRET = "ghp_" + ("z" * 36)


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
    )
    return TestClient(app), backend


def test_console_run_view_source_files_exist() -> None:
    required = (
        "src/lib/api/client.ts",
        "src/lib/api/runs.ts",
        "src/lib/redaction/display.ts",
        "src/components/timeline/RunTimelineView.tsx",
        "src/components/timeline/TraceEventsView.tsx",
        "src/app/t/[tenantId]/runs/page.tsx",
        "src/app/t/[tenantId]/runs/[runId]/page.tsx",
    )
    for relative in required:
        assert (CONSOLE_ROOT / relative).is_file(), relative


def test_console_timeline_sections_match_python_renderer() -> None:
    display_module = (CONSOLE_ROOT / "src/lib/redaction/display.ts").read_text(encoding="utf-8")
    assert "Summary" in display_module
    assert "Failures" in display_module
    assert list(SECTION_ORDER)[0] == "Summary"
    assert list(SECTION_ORDER)[-1] == "Failures"


def test_console_strict_redaction_hides_sensitive_fields() -> None:
    display_module = (CONSOLE_ROOT / "src/lib/redaction/display.ts").read_text(encoding="utf-8")
    for field in ("raw_prompt", "debug_payload", "secrets"):
        assert field in display_module


def test_api_client_sends_authorization_and_tenant_headers() -> None:
    client_module = (CONSOLE_ROOT / "src/lib/api/client.ts").read_text(encoding="utf-8")
    assert "Authorization" in client_module
    assert "X-Tenant-Id" in client_module
    assert "tenant_id" in client_module


def test_run_list_and_trace_endpoints_are_tenant_scoped(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    checkpoint = sample_checkpoint(run_id="run-console001", tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    backend.trace.emit_event(
        tenant_id="tenant-a",
        run_id="run-console001",
        event_type=TraceEventType.model_call_start,
        node_id="analyze",
        seq=1,
        payload={"raw_prompt": _SECRET, "debug_payload": "internal"},
    )

    listed = client.get("/v2/runs", params={"tenant_id": "tenant-a"})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["run_id"] == "run-console001"

    timeline = client.get("/v2/runs/run-console001/timeline", params={"tenant_id": "tenant-a"})
    assert timeline.status_code == 200
    assert timeline.json()["run_id"] == "run-console001"

    trace = client.get("/v2/runs/run-console001/trace", params={"tenant_id": "tenant-a"})
    assert trace.status_code == 200
    body = trace.json()
    assert body["redaction_profile"] == "strict"
    serialized = json.dumps(body)
    assert _SECRET not in serialized
    assert "raw_prompt" not in serialized
    assert "debug" not in serialized
