"""Approval request persistence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from safecode.context.redactor import redact_secrets
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import emit_standalone_trace
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestExistsError,
    ApprovalRequestNotFoundError,
    ApprovalRequestTamperedError,
    InvalidRunIdError,
    RequestAlreadyConsumedError,
    WorkflowError,
)
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.enterprise.workflow.types import RiskTier
from safecode.utils.file_lock import atomic_replace_text, keyed_exclusive_lock, lock_path_for


class Action(str, Enum):
    file_write = "file_write"
    command_execute = "command_execute"
    scanner_run = "scanner_run"
    github_read = "github_read"
    github_write_comment = "github_write_comment"
    github_branch_push = "github_branch_push"
    github_pr_create = "github_pr_create"
    issue_comment = "issue_comment"
    mcp_read = "mcp_read"
    mcp_write = "mcp_write"
    retrieval_source_access = "retrieval_source_access"
    memory_fact_inject = "memory_fact_inject"
    policy_config_change = "policy_config_change"
    production_access = "production_access"


ApprovalStatus = Literal["pending", "approved", "rejected", "evidence_requested", "revoked"]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    tenant_id: str = "local"
    action: Action
    risk_tier: RiskTier
    requested_by_node: str
    requesting_actor: str
    target: dict[str, str] = Field(default_factory=dict)
    preview: str = ""
    policy_snapshot_id: str
    status: ApprovalStatus = "pending"
    created_at: str
    decision_at: str | None = None
    decision_actor: str | None = None
    decision_note: str | None = None
    request_hash: str = ""


class ApprovalDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    decision: Literal["approved", "rejected"]
    decision_actor: str
    decision_note: str = ""
    decided_at: str
    request_hash: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def request_hash(request: ApprovalRequest) -> str:
    payload = request.model_copy(update={"request_hash": ""}).model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approvals_dir(sac_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    root = (sac_root / "enterprise" / "runs").resolve()
    directory = (root / run_id / "approvals").resolve()
    if root not in directory.parents:
        raise InvalidRunIdError(f"approval path escapes runs root for {run_id!r}")
    return directory


def _atomic_write(path: Path, payload: dict) -> None:
    with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
        atomic_replace_text(path, json.dumps(payload, sort_keys=True, indent=2))


_REQUEST_ID_RE = re.compile(r"^approval-[a-zA-Z0-9_-]{8,64}$")


def validate_request_id(request_id: str) -> str:
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.match(request_id):
        raise InvalidRunIdError(f"invalid request_id: {request_id!r}")
    if ".." in request_id or "/" in request_id or "\\" in request_id:
        raise InvalidRunIdError(f"invalid request_id path characters: {request_id!r}")
    return request_id


def save_request(sac_root: Path, request: ApprovalRequest) -> ApprovalRequest:
    validate_request_id(request.request_id)
    directory = approvals_dir(sac_root, request.run_id)
    path = directory / f"{request.request_id}.json"
    with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
        if path.exists():
            raise ApprovalRequestExistsError(f"approval request exists: {request.request_id}")
        redacted = request.model_copy(update={"preview": redact_secrets(request.preview)[:4096]})
        redacted = redacted.model_copy(update={"request_hash": request_hash(redacted)})
        atomic_replace_text(path, json.dumps(json.loads(redacted.model_dump_json()), sort_keys=True, indent=2))
    emit_standalone_trace(
        sac_root,
        run_id=redacted.run_id,
        tenant_id=redacted.tenant_id,
        event_type=TraceEventType.approval_requested,
        node_id=redacted.requested_by_node,
        actor_id=redacted.requesting_actor,
        policy_snapshot_id=redacted.policy_snapshot_id,
        payload={
            "request_id": redacted.request_id,
            "action": redacted.action.value,
            "risk_tier": redacted.risk_tier.value,
            "status": redacted.status,
        },
    )
    return redacted


def load_request(sac_root: Path, run_id: str, request_id: str) -> ApprovalRequest:
    validate_request_id(request_id)
    path = approvals_dir(sac_root, run_id) / f"{request_id}.json"
    if not path.is_file():
        raise ApprovalRequestNotFoundError(f"approval request not found: {request_id}")
    request = ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
    if request.request_hash != request_hash(request):
        raise ApprovalRequestTamperedError(f"approval request tampered: {request_id}")
    return request


def list_requests(sac_root: Path, run_id: str) -> list[ApprovalRequest]:
    directory = approvals_dir(sac_root, run_id)
    if not directory.is_dir():
        return []
    items: list[ApprovalRequest] = []
    for path in sorted(directory.glob("*.json")):
        request = ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
        if request.request_hash != request_hash(request):
            raise ApprovalRequestTamperedError(f"approval request tampered: {request.request_id}")
        items.append(request)
    return items


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_id: str
    run_id: str
    request_id: str
    tenant_id: str = "local"
    action: Action
    policy_snapshot_id: str
    target: dict[str, str] = Field(default_factory=dict)
    created_at: str
    consumed_at: str | None = None
    revoked_at: str | None = None
    grant_hash: str = ""


class GrantAlreadyConsumedError(WorkflowError):
    """Raised when a grant is consumed more than once."""


def grant_hash(grant: Grant) -> str:
    payload = grant.model_copy(update={"grant_hash": ""}).model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_GRANT_ID_RE = re.compile(r"^grant-[a-zA-Z0-9_-]{8,64}$")


def validate_grant_id(grant_id: str) -> str:
    if not isinstance(grant_id, str) or not _GRANT_ID_RE.match(grant_id):
        raise InvalidRunIdError(f"invalid grant_id: {grant_id!r}")
    if ".." in grant_id or "/" in grant_id or "\\" in grant_id:
        raise InvalidRunIdError(f"invalid grant_id path characters: {grant_id!r}")
    return grant_id


def grants_dir(sac_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    root = (sac_root / "enterprise" / "runs").resolve()
    directory = (root / run_id / "grants").resolve()
    if root not in directory.parents:
        raise InvalidRunIdError(f"grant path escapes runs root for {run_id!r}")
    return directory


def save_grant(sac_root: Path, grant: Grant) -> Grant:
    validate_grant_id(grant.grant_id)
    directory = grants_dir(sac_root, grant.run_id)
    path = directory / f"{grant.grant_id}.json"
    with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
        if path.exists():
            raise ApprovalRequestExistsError(f"grant exists: {grant.grant_id}")
        stored = grant.model_copy(update={"grant_hash": grant_hash(grant)})
        atomic_replace_text(path, json.dumps(json.loads(stored.model_dump_json()), sort_keys=True, indent=2))
    return stored


def load_grant(sac_root: Path, run_id: str, grant_id: str) -> Grant:
    validate_grant_id(grant_id)
    path = grants_dir(sac_root, run_id) / f"{grant_id}.json"
    if not path.is_file():
        raise ApprovalRequestNotFoundError(f"grant not found: {grant_id}")
    grant = Grant.model_validate_json(path.read_text(encoding="utf-8"))
    if grant.grant_hash != grant_hash(grant):
        raise ApprovalRequestTamperedError(f"grant tampered: {grant_id}")
    return grant


def consume_grant(sac_root: Path, run_id: str, grant_id: str) -> Grant:
    path = grants_dir(sac_root, run_id) / f"{grant_id}.json"
    with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
        grant = load_grant(sac_root, run_id, grant_id)
        if grant.revoked_at is not None:
            raise GrantAlreadyConsumedError(f"grant revoked: {grant_id}")
        if grant.consumed_at is not None:
            raise GrantAlreadyConsumedError(f"grant already consumed: {grant_id}")
        updated = grant.model_copy(update={"consumed_at": _utc_now()})
        updated = updated.model_copy(update={"grant_hash": grant_hash(updated)})
        atomic_replace_text(path, json.dumps(json.loads(updated.model_dump_json()), sort_keys=True, indent=2))
    emit_standalone_trace(
        sac_root,
        run_id=run_id,
        tenant_id=updated.tenant_id,
        event_type=TraceEventType.approval_consumed,
        node_id="approval_store",
        actor_id=None,
        policy_snapshot_id=updated.policy_snapshot_id,
        payload={
            "grant_id": grant_id,
            "request_id": updated.request_id,
            "action": updated.action.value,
        },
    )
    return updated


def grant_id_for_request(request: ApprovalRequest) -> str:
    digest = hashlib.sha256(request.request_hash.encode("utf-8")).hexdigest()[:20]
    return f"grant-{digest}"


def validate_approved_request(
    sac_root: Path,
    run_id: str,
    request_id: str,
    *,
    tenant_id: str,
    action: Action,
    policy_snapshot_id: str,
    target: dict[str, str],
) -> tuple[ApprovalRequest, Grant]:
    """Validate an approval and its grant against the exact pending action."""
    request = load_request(sac_root, run_id, request_id)
    if request.status != "approved":
        raise PermissionError(f"approval request is not approved: {request_id}")
    expected = (tenant_id, action, policy_snapshot_id, target)
    actual = (request.tenant_id, request.action, request.policy_snapshot_id, request.target)
    if actual != expected:
        raise PermissionError(f"approval request binding mismatch: {request_id}")
    grant = load_grant(sac_root, run_id, grant_id_for_request(request))
    grant_binding = (grant.tenant_id, grant.action, grant.policy_snapshot_id, grant.target)
    if grant.request_id != request.request_id or grant_binding != expected:
        raise PermissionError(f"approval grant binding mismatch: {grant.grant_id}")
    if grant.revoked_at is not None or grant.consumed_at is not None:
        raise GrantAlreadyConsumedError(f"approval grant unavailable: {grant.grant_id}")
    return request, grant


def consume_approved_request(
    sac_root: Path,
    run_id: str,
    request_id: str,
    *,
    tenant_id: str,
    action: Action,
    policy_snapshot_id: str,
    target: dict[str, str],
) -> Grant:
    _, grant = validate_approved_request(
        sac_root,
        run_id,
        request_id,
        tenant_id=tenant_id,
        action=action,
        policy_snapshot_id=policy_snapshot_id,
        target=target,
    )
    return consume_grant(sac_root, run_id, grant.grant_id)


def decide_request(
    sac_root: Path,
    run_id: str,
    request_id: str,
    *,
    decision: Literal["approved", "rejected", "evidence_requested", "revoked"],
    decision_actor: str,
    decision_note: str = "",
) -> ApprovalRequest:
    if decision_actor.startswith("model:"):
        raise PermissionError("model actors cannot approve their own requests")
    path = approvals_dir(sac_root, run_id) / f"{request_id}.json"
    with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
        request = load_request(sac_root, run_id, request_id)
        if request.status not in {"pending", "evidence_requested"} and decision in {"approved", "rejected"}:
            raise RequestAlreadyConsumedError(f"approval request already decided: {request_id}")
        if decision == "revoked" and request.status not in {"pending", "evidence_requested", "approved"}:
            raise RequestAlreadyConsumedError(f"approval request cannot be revoked: {request_id}")
        updated = request.model_copy(
            update={
                "status": decision,
                "decision_at": _utc_now(),
                "decision_actor": decision_actor,
                "decision_note": redact_secrets(decision_note),
            }
        )
        updated = updated.model_copy(update={"request_hash": request_hash(updated)})
        atomic_replace_text(path, json.dumps(json.loads(updated.model_dump_json()), sort_keys=True, indent=2))
        if decision == "approved":
            save_grant(
                sac_root,
                Grant(
                    grant_id=grant_id_for_request(updated),
                    run_id=updated.run_id,
                    request_id=updated.request_id,
                    tenant_id=updated.tenant_id,
                    action=updated.action,
                    policy_snapshot_id=updated.policy_snapshot_id,
                    target=updated.target,
                    created_at=updated.decision_at or _utc_now(),
                ),
            )
        elif decision == "revoked" and request.status == "approved":
            grant_id = grant_id_for_request(request)
            grant_path = grants_dir(sac_root, run_id) / f"{grant_id}.json"
            with keyed_exclusive_lock(str(grant_path.resolve()), lock_path_for(grant_path)):
                grant = load_grant(sac_root, run_id, grant_id)
                revoked = grant.model_copy(update={"revoked_at": updated.decision_at or _utc_now()})
                revoked = revoked.model_copy(update={"grant_hash": grant_hash(revoked)})
                atomic_replace_text(
                    grant_path,
                    json.dumps(json.loads(revoked.model_dump_json()), sort_keys=True, indent=2),
                )
    if decision in {"approved", "rejected"}:
        event_type = (
            TraceEventType.approval_decided
            if decision == "approved"
            else TraceEventType.approval_rejected
        )
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=updated.tenant_id,
            event_type=event_type,
            node_id="approval_store",
            actor_id=decision_actor,
            policy_snapshot_id=updated.policy_snapshot_id,
            payload={
                "request_id": request_id,
                "action": updated.action.value,
                "decision": decision,
                "status": updated.status,
            },
        )
    return updated


def request_evidence(
    sac_root: Path,
    run_id: str,
    request_id: str,
    *,
    decision_actor: str,
    decision_note: str,
) -> ApprovalRequest:
    if not decision_note.strip():
        raise ValueError("evidence request requires a note")
    return decide_request(
        sac_root,
        run_id,
        request_id,
        decision="evidence_requested",
        decision_actor=decision_actor,
        decision_note=decision_note,
    )


def revoke_request(
    sac_root: Path,
    run_id: str,
    request_id: str,
    *,
    decision_actor: str,
    decision_note: str = "",
) -> ApprovalRequest:
    return decide_request(
        sac_root,
        run_id,
        request_id,
        decision="revoked",
        decision_actor=decision_actor,
        decision_note=decision_note,
    )


def list_pending_requests(sac_root: Path, run_id: str) -> list[ApprovalRequest]:
    return [item for item in list_requests(sac_root, run_id) if item.status == "pending"]
