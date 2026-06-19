"""Approval command endpoint tests (v2.1.5-T2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "persistence"))
from backend_contract import sample_checkpoint, sample_request  # noqa: E402

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.approvals.store import GrantAlreadyConsumedError, grant_id_for_request
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role

_HEADERS = {
    "X-Tenant-Id": "tenant-a",
    "Idempotency-Key": "approval-cmd-001",
}


def _client(tmp_path: Path, *, role: Role = Role.maintainer) -> tuple[TestClient, LocalBackend]:
    def _resolve() -> RBACSubject:
        return RBACSubject(
            actor_id="user:reviewer",
            tenant_id="tenant-a",
            roles=(role,),
        )

    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:reviewer"}
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=_resolve,
        project_root=tmp_path,
    )
    return TestClient(app), backend


def _seed_pending(backend: LocalBackend, *, request_id: str = "approval-pending01") -> str:
    run_id = "run-approval001"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    request = sample_request(run_id=run_id, request_id=request_id, tenant_id="tenant-a")
    request = request.model_copy(update={"requesting_actor": "user:requester"})
    backend.approvals.save_request(tenant_id="tenant-a", request=request)
    return request_id


def test_approve_and_reject_emit_status(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend)
    approved = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved", "rationale": "looks good"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    request_id_2 = _seed_pending(backend, request_id="approval-pending02")
    rejected = client.post(
        f"/v2/approvals/{request_id_2}/decide",
        headers={**_HEADERS, "Idempotency-Key": "approval-cmd-002"},
        json={"decision": "rejected", "rationale": "no"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_self_approval_fails_closed(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-approval001"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    request = sample_request(
        run_id=run_id, request_id="approval-self0001", tenant_id="tenant-a"
    ).model_copy(update={"requesting_actor": "user:reviewer"})
    backend.approvals.save_request(tenant_id="tenant-a", request=request)
    response = client.post(
        f"/v2/approvals/{request.request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved"},
    )
    assert response.status_code == 403


def test_unauthorized_role_fails_closed(tmp_path: Path) -> None:
    client, backend = _client(tmp_path, role=Role.viewer)
    request_id = _seed_pending(backend, request_id="approval-pending03")
    response = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers={**_HEADERS, "Idempotency-Key": "approval-cmd-003"},
        json={"decision": "approved"},
    )
    assert response.status_code == 403


def test_consumed_grant_replay_rejected(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend, request_id="approval-pending04")
    approved = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers={**_HEADERS, "Idempotency-Key": "approval-cmd-004"},
        json={"decision": "approved"},
    )
    assert approved.status_code == 200
    grant_id = grant_id_for_request(
        backend.approvals.load_request(
            tenant_id="tenant-a", run_id="run-approval001", request_id=request_id
        )
    )
    backend.approvals.consume_grant(
        tenant_id="tenant-a", run_id="run-approval001", grant_id=grant_id
    )
    with pytest.raises(GrantAlreadyConsumedError):
        backend.approvals.consume_grant(
            tenant_id="tenant-a", run_id="run-approval001", grant_id=grant_id
        )
