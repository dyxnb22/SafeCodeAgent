"""Approval request store tests."""

import json
from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    decide_request,
    grant_id_for_request,
    list_requests,
    load_grant,
    load_request,
    save_request,
)
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestExistsError,
    ApprovalRequestNotFoundError,
    ApprovalRequestTamperedError,
    InvalidRunIdError,
    RequestAlreadyConsumedError,
)
from safecode.enterprise.workflow.types import RiskTier


def _request(run_id: str = "run-approval01", request_id: str = "approval-run-approval01") -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        run_id=run_id,
        action=Action.file_write,
        risk_tier=RiskTier.high,
        requested_by_node="approval_gate",
        requesting_actor="user:test",
        policy_snapshot_id="snapshot-local",
        created_at="2026-06-19T00:00:00+00:00",
        preview="secret=REDACTED_TOKEN",
    )


def test_save_and_load_request(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    saved = save_request(sac_root, _request())
    loaded = load_request(sac_root, saved.run_id, saved.request_id)
    assert loaded.status == "pending"
    assert loaded.request_hash


def test_duplicate_request_raises(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    save_request(sac_root, _request())
    with pytest.raises(ApprovalRequestExistsError):
        save_request(sac_root, _request())


def test_decide_request_approve_and_reject(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    req = save_request(sac_root, _request())
    approved = decide_request(
        sac_root, req.run_id, req.request_id, decision="approved", decision_actor="user:approver"
    )
    assert approved.status == "approved"
    grant = load_grant(sac_root, req.run_id, grant_id_for_request(approved))
    assert grant.request_id == approved.request_id
    assert grant.action == approved.action
    assert grant.policy_snapshot_id == approved.policy_snapshot_id
    with pytest.raises(RequestAlreadyConsumedError):
        decide_request(
            sac_root, req.run_id, req.request_id, decision="approved", decision_actor="user:approver"
        )


def test_model_cannot_approve_itself(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    req = save_request(sac_root, _request())
    with pytest.raises(PermissionError):
        decide_request(
            sac_root, req.run_id, req.request_id, decision="approved", decision_actor="model:agent"
        )


def test_self_approval_rejected(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    req = save_request(sac_root, _request())
    with pytest.raises(PermissionError, match="self-approval"):
        decide_request(
            sac_root,
            req.run_id,
            req.request_id,
            decision="approved",
            decision_actor=req.requesting_actor,
        )
    loaded = load_request(sac_root, req.run_id, req.request_id)
    assert loaded.status == "pending"


def test_decide_request_rejects_cross_tenant_before_write(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    req = save_request(
        sac_root,
        _request(run_id="run-tenant-guard1", request_id="approval-tenant-guard1").model_copy(
            update={"tenant_id": "tenant-a"}
        ),
    )
    with pytest.raises(PermissionError, match="tenant boundary violation"):
        decide_request(
            sac_root,
            req.run_id,
            req.request_id,
            decision="approved",
            decision_actor="user:approver",
            expected_tenant_id="tenant-b",
        )
    loaded = load_request(sac_root, req.run_id, req.request_id)
    assert loaded.status == "pending"


def test_tampered_request_invalidates(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    req = save_request(sac_root, _request())
    path = sac_root / "enterprise" / "runs" / req.run_id / "approvals" / f"{req.request_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["preview"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ApprovalRequestTamperedError):
        load_request(sac_root, req.run_id, req.request_id)
    with pytest.raises(ApprovalRequestTamperedError):
        list_requests(sac_root, req.run_id)


def test_run_id_and_request_id_traversal_rejected(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    with pytest.raises(InvalidRunIdError):
        save_request(sac_root, _request(run_id="../escape", request_id="approval-run-escape0001"))
    with pytest.raises(InvalidRunIdError):
        save_request(sac_root, _request(request_id="../bad"))


def test_list_requests_isolated_by_run(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    save_request(sac_root, _request(run_id="run-isolated01", request_id="approval-run-isolated01"))
    save_request(sac_root, _request(run_id="run-isolated02", request_id="approval-run-isolated02"))
    assert len(list_requests(sac_root, "run-isolated01")) == 1


def test_missing_request_not_found(tmp_path: Path):
    with pytest.raises(ApprovalRequestNotFoundError):
        load_request(tmp_path / ".sac", "run-missing001", "approval-run-missing001")
