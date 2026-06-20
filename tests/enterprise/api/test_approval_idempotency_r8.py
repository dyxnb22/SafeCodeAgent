"""R8 approval API idempotency and resume regression tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "persistence"))
from backend_contract import sample_checkpoint, sample_request  # noqa: E402

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.approval_service import decide_approval
from safecode.enterprise.api.exceptions import ApprovalForbiddenError
from safecode.enterprise.api.idempotency import approval_resume_idempotency_key
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role

_HEADERS = {
    "X-Tenant-Id": "tenant-a",
    "Idempotency-Key": "approval-idem-001",
}


def _client(tmp_path: Path, *, role: Role = Role.maintainer) -> tuple[TestClient, LocalBackend]:
    def _resolve() -> RBACSubject:
        return RBACSubject(actor_id="user:reviewer", tenant_id="tenant-a", roles=(role,))

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


def _seed_pending(
    backend: LocalBackend,
    *,
    request_id: str = "approval-pending01",
    tenant_id: str = "tenant-a",
    run_id: str = "run-approval001",
) -> str:
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id=tenant_id)
    backend.runs.save_checkpoint(tenant_id=tenant_id, checkpoint=checkpoint)
    request = sample_request(run_id=run_id, request_id=request_id, tenant_id=tenant_id)
    request = request.model_copy(update={"requesting_actor": "user:requester"})
    backend.approvals.save_request(tenant_id=tenant_id, request=request)
    return request_id


def test_decide_same_key_replay_returns_identical_payload(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend)
    first = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved", "rationale": "ok"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved", "rationale": "ok"},
    )
    assert second.status_code == 200
    assert second.json() == first.json()


def test_same_key_different_decision_returns_409(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend)
    first = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved"},
    )
    assert first.status_code == 200
    conflict = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers={**_HEADERS, "Idempotency-Key": _HEADERS["Idempotency-Key"]},
        json={"decision": "rejected"},
    )
    assert conflict.status_code == 409


def test_same_key_different_approval_id_returns_409(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend, request_id="approval-pending01")
    _seed_pending(backend, request_id="approval-pending02")
    first = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved"},
    )
    assert first.status_code == 200
    conflict = client.post(
        "/v2/approvals/approval-pending02/decide",
        headers=_HEADERS,
        json={"decision": "approved"},
    )
    assert conflict.status_code == 409


def test_cross_tenant_same_key_is_independent(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_a = _seed_pending(backend, request_id="approval-pending01", tenant_id="tenant-a")
    request_b = _seed_pending(
        backend,
        request_id="approval-pending99",
        tenant_id="tenant-b",
        run_id="run-approval099",
    )

    def _resolve_a() -> RBACSubject:
        return RBACSubject(actor_id="user:reviewer", tenant_id="tenant-a", roles=(Role.maintainer,))

    def _resolve_b() -> RBACSubject:
        return RBACSubject(actor_id="user:reviewer", tenant_id="tenant-b", roles=(Role.maintainer,))

    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:reviewer"}
    )
    app_a = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=_resolve_a,
        project_root=tmp_path,
    )
    app_b = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=_resolve_b,
        project_root=tmp_path,
    )
    headers = {"X-Tenant-Id": "tenant-a", "Idempotency-Key": "shared-key-12345678"}
    assert TestClient(app_a).post(
        f"/v2/approvals/{request_a}/decide",
        headers=headers,
        json={"decision": "approved"},
    ).status_code == 200
    headers_b = {"X-Tenant-Id": "tenant-b", "Idempotency-Key": "shared-key-12345678"}
    assert TestClient(app_b).post(
        f"/v2/approvals/{request_b}/decide",
        headers=headers_b,
        json={"decision": "approved"},
    ).status_code == 200


def test_approve_enqueues_resume_job(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend)
    response = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers={**_HEADERS, "Idempotency-Key": "approval-resume-01"},
        json={"decision": "approved"},
    )
    assert response.status_code == 200
    resume_key = approval_resume_idempotency_key(
        tenant_id="tenant-a", approval_id=request_id, decision="approved"
    )
    record = backend.commands.get_command(tenant_id="tenant-a", idempotency_key=resume_key)
    assert record is not None
    assert record.command == "resume"
    pending = backend.sac_root / "enterprise" / "worker" / "queue" / "pending.jsonl"
    assert pending.is_file()
    lines = [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(item["command"] == "resume" for item in lines)


def test_reject_enqueues_resume_job(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend, request_id="approval-pending99")
    response = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers={**_HEADERS, "Idempotency-Key": "approval-resume-02"},
        json={"decision": "rejected"},
    )
    assert response.status_code == 200
    resume_key = approval_resume_idempotency_key(
        tenant_id="tenant-a", approval_id=request_id, decision="rejected"
    )
    assert backend.commands.get_command(tenant_id="tenant-a", idempotency_key=resume_key) is not None


def test_replay_does_not_duplicate_resume_or_audit(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend, request_id="approval-pending55")
    headers = {**_HEADERS, "Idempotency-Key": "approval-dedupe-01"}
    first = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=headers,
        json={"decision": "approved"},
    )
    assert first.status_code == 200
    audit_count = len(backend.audit.list_events(tenant_id="tenant-a", run_id="run-approval001"))
    second = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=headers,
        json={"decision": "approved"},
    )
    assert second.status_code == 200
    assert len(backend.audit.list_events(tenant_id="tenant-a", run_id="run-approval001")) == audit_count
    pending = backend.sac_root / "enterprise" / "worker" / "queue" / "pending.jsonl"
    resume_jobs = [
        json.loads(line)
        for line in pending.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["command"] == "resume"
    ]
    assert len(resume_jobs) == 1


def test_cached_replay_still_enforces_approval_authorization(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    request_id = _seed_pending(backend)
    response = client.post(
        f"/v2/approvals/{request_id}/decide",
        headers=_HEADERS,
        json={"decision": "approved", "rationale": "ok"},
    )
    assert response.status_code == 200

    with pytest.raises(ApprovalForbiddenError, match="self-approval"):
        decide_approval(
            backend,
            tenant_id="tenant-a",
            approval_id=request_id,
            subject=RBACSubject(
                actor_id="user:requester",
                tenant_id="tenant-a",
                roles=(Role.maintainer,),
            ),
            decision="approved",
            rationale="ok",
            idempotency_key=_HEADERS["Idempotency-Key"],
        )
