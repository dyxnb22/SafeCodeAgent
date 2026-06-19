"""Approval command handlers for the Team Server API (v2.1.5-T2)."""

from __future__ import annotations

from safecode.enterprise.api.exceptions import ApprovalForbiddenError, ApprovalRequestNotFoundError
from safecode.enterprise.api.read_service import list_approvals
from safecode.enterprise.approvals.store import ApprovalRequest
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.rbac.models import RBACSubject, ROLE_RANK
from safecode.enterprise.rbac.permissions import minimum_approval_role
from safecode.enterprise.workflow.exceptions import RequestAlreadyConsumedError


def resolve_approval(
    backend: object,
    *,
    tenant_id: str,
    approval_id: str,
) -> ApprovalRequest:
    for request in list_approvals(backend, tenant_id=tenant_id):
        if request.request_id == approval_id:
            return request
    raise ApprovalRequestNotFoundError(f"approval request not found: {approval_id}")


def _assert_can_decide(subject: RBACSubject, request: ApprovalRequest) -> None:
    if subject.actor_id == request.requesting_actor:
        raise ApprovalForbiddenError("self-approval is not allowed")
    if subject.actor_id.startswith("model:"):
        raise ApprovalForbiddenError("model actors cannot approve requests")
    required = minimum_approval_role(request.action)
    if required is None:
        return
    if ROLE_RANK[subject.highest_role()] < ROLE_RANK[required]:
        raise ApprovalForbiddenError(
            f"role {subject.highest_role().value!r} cannot approve action {request.action.value!r}"
        )


def decide_approval(
    backend: object,
    *,
    tenant_id: str,
    approval_id: str,
    subject: RBACSubject,
    decision: str,
    rationale: str = "",
) -> dict[str, str]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    request = resolve_approval(backend, tenant_id=tenant_id, approval_id=approval_id)
    _assert_can_decide(subject, request)
    try:
        updated = backend.approvals.decide_request(
            tenant_id=tenant_id,
            run_id=request.run_id,
            request_id=request.request_id,
            decision=decision,  # type: ignore[arg-type]
            decision_actor=subject.actor_id,
            decision_note=rationale,
        )
    except RequestAlreadyConsumedError as exc:
        raise ApprovalForbiddenError(str(exc)) from exc
    backend.audit.emit(
        AuditEventKind.approval_decided,
        tenant_id=tenant_id,
        run_id=request.run_id,
        actor_id=subject.actor_id,
        payload={
            "approval_id": approval_id,
            "decision": decision,
        },
    )
    return {"approval_id": updated.request_id, "status": updated.status}


def revoke_approval_grant(
    backend: object,
    *,
    tenant_id: str,
    approval_id: str,
    subject: RBACSubject,
    rationale: str = "",
) -> dict[str, str]:
    request = resolve_approval(backend, tenant_id=tenant_id, approval_id=approval_id)
    _assert_can_decide(subject, request)
    try:
        updated = backend.approvals.revoke_request(
            tenant_id=tenant_id,
            run_id=request.run_id,
            request_id=request.request_id,
            decision_actor=subject.actor_id,
            decision_note=rationale,
        )
    except RequestAlreadyConsumedError as exc:
        raise ApprovalForbiddenError(str(exc)) from exc
    backend.audit.emit(
        AuditEventKind.approval_decided,
        tenant_id=tenant_id,
        run_id=request.run_id,
        actor_id=subject.actor_id,
        payload={
            "approval_id": approval_id,
            "decision": "revoked",
        },
    )
    return {"approval_id": updated.request_id, "status": updated.status}
