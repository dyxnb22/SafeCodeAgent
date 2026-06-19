"""Run command endpoint tests (v2.1.5-T1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.types import WorkflowStatus

_ROOT = Path(__file__).resolve().parents[3]


def _subject_resolver(tenant_id: str = "tenant-a", role: Role = Role.developer) -> callable:
    def _resolve() -> RBACSubject:
        return RBACSubject(actor_id="user:dev", tenant_id=tenant_id, roles=(role,))

    return _resolve


def _client(
    tmp_path: Path, *, tenant_id: str = "tenant-a", role: Role = Role.developer
) -> tuple[TestClient, LocalBackend]:
    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:dev"}
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=_subject_resolver(tenant_id=tenant_id, role=role),
        project_root=tmp_path,
    )
    return TestClient(app), backend


def _headers(*, tenant_id: str = "tenant-a", idempotency_key: str | None = "idem-key-001") -> dict[str, str]:
    headers = {"X-Tenant-Id": tenant_id}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_start_run_is_idempotent(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    body = {"task_type": "pr_review", "input_ref": str(fixture)}
    first = client.post("/v2/runs", headers=_headers(), json=body)
    second = client.post("/v2/runs", headers=_headers(), json=body)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    assert first.json()["status"] == "pending"
    checkpoint = load_checkpoint(backend.sac_root, first.json()["run_id"])
    assert checkpoint.state.status is WorkflowStatus.pending


def test_missing_idempotency_key_fails_closed(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    response = client.post(
        "/v2/runs",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"task_type": "pr_review", "input_ref": "fixture.json"},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


def test_cancel_marks_non_terminal_run_cancelled(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    started = client.post(
        "/v2/runs",
        headers=_headers(idempotency_key="start-key-001"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    run_id = started.json()["run_id"]
    cancelled = client.post(
        f"/v2/runs/{run_id}/cancel",
        headers=_headers(idempotency_key="cancel-key-001"),
    )
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"
    checkpoint = load_checkpoint(backend.sac_root, run_id)
    assert checkpoint.state.status is WorkflowStatus.cancelled


def test_cancel_is_noop_for_terminal_run(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    started = client.post(
        "/v2/runs",
        headers=_headers(idempotency_key="start-key-002"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    run_id = started.json()["run_id"]
    checkpoint = load_checkpoint(backend.sac_root, run_id)
    terminal = checkpoint.state.model_copy(update={"status": WorkflowStatus.succeeded})
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint

    backend.runs.save_checkpoint(
        tenant_id="tenant-a",
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=run_id,
            completed_nodes=list(checkpoint.completed_nodes),
            next_node=checkpoint.next_node,
            state=terminal,
        ),
    )
    response = client.post(
        f"/v2/runs/{run_id}/cancel",
        headers=_headers(idempotency_key="cancel-key-002"),
    )
    assert response.status_code == 202
    assert response.json()["status"] == "succeeded"


def test_cross_tenant_cancel_rejected(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path, tenant_id="tenant-a")
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    started = client.post(
        "/v2/runs",
        headers=_headers(tenant_id="tenant-a", idempotency_key="start-key-003"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    run_id = started.json()["run_id"]
    response = client.post(
        f"/v2/runs/{run_id}/cancel",
        headers=_headers(tenant_id="tenant-b", idempotency_key="cancel-key-003"),
    )
    assert response.status_code == 403


def test_resume_enqueues_existing_run(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    started = client.post(
        "/v2/runs",
        headers=_headers(idempotency_key="start-key-004"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    run_id = started.json()["run_id"]
    resumed = client.post(
        f"/v2/runs/{run_id}/resume",
        headers=_headers(idempotency_key="resume-key-004"),
    )
    assert resumed.status_code == 202
    assert resumed.json()["run_id"] == run_id
    pending = (backend.sac_root / "enterprise" / "worker" / "queue" / "pending.jsonl")
    assert pending.is_file()
    lines = pending.read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["command"] == "resume" for line in lines if line.strip())


def test_viewer_cannot_start_runs(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path, role=Role.viewer)
    response = client.post(
        "/v2/runs",
        headers=_headers(),
        json={"task_type": "pr_review", "input_ref": "fixture.json"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("command", ["resume", "cancel"])
def test_viewer_cannot_mutate_existing_runs(tmp_path: Path, command: str) -> None:
    developer, _backend = _client(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    started = developer.post(
        "/v2/runs",
        headers=_headers(idempotency_key="start-viewer-test"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    viewer, _backend = _client(tmp_path, role=Role.viewer)
    response = viewer.post(
        f"/v2/runs/{started.json()['run_id']}/{command}",
        headers=_headers(idempotency_key=f"{command}-viewer-test"),
    )
    assert response.status_code == 403
