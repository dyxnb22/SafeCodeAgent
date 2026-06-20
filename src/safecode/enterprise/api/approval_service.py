"""Approval command handlers for the Team Server API (v2.1.5-T2)."""

from __future__ import annotations

from safecode.enterprise.api.exceptions import ApprovalForbiddenError, ApprovalRequestNotFoundError
from safecode.enterprise.api.idempotency import (
    ApprovalIdempotencyRecord,
    api_idempotency_for,
    approval_request_fingerprint,
)
from safecode.enterprise.api.read_service import list_approvals
from safecode.enterprise.approvals.resume import ensure_approval_resume_enqueued
from safecode.enterprise.approvals.store import ApprovalRequest
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.rbac.models import RBACSubject, ROLE_RANK
from safecode.enterprise.rbac.permissions import minimum_approval_role
from safecode.enterprise.worker.queue import IdempotencyConflictError
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
    idempotency_key: str,
) -> dict[str, str]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    store = api_idempotency_for(backend)
    fingerprint = approval_request_fingerprint(
        operation="decide",
        approval_id=approval_id,
        decision=decision,
        rationale=rationale,
    )
    request = resolve_approval(backend, tenant_id=tenant_id, approval_id=approval_id)
    _assert_can_decide(subject, request)
    cached = store.get(tenant_id=tenant_id, idempotency_key=idempotency_key)
    if cached is not None:
        if cached.request_fingerprint != fingerprint:
            raise IdempotencyConflictError(
                f"idempotency key {idempotency_key!r} already bound to another request"
            )
        return dict(cached.response)

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
        updated = backend.approvals.load_request(
            tenant_id=tenant_id,
            run_id=request.run_id,
            request_id=request.request_id,
        )
        if updated.status != decision:
            raise ApprovalForbiddenError(str(exc)) from exc

    ensure_approval_resume_enqueued(
        backend,
        tenant_id=tenant_id,
        request=updated,
        decision=decision,
    )
    response = {"approval_id": updated.request_id, "status": updated.status}
    store.save(
        ApprovalIdempotencyRecord(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            operation="decide",
            request_fingerprint=fingerprint,
            response=response,
            created_at=updated.decision_at or "",
        )
    )
    if cached is None:
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
    return response


def revoke_approval_grant(
    backend: object,
    *,
    tenant_id: str,
    approval_id: str,
    subject: RBACSubject,
    rationale: str = "",
    idempotency_key: str,
) -> dict[str, str]:
    store = api_idempotency_for(backend)
    fingerprint = approval_request_fingerprint(
        operation="revoke",
        approval_id=approval_id,
        rationale=rationale,
    )
    request = resolve_approval(backend, tenant_id=tenant_id, approval_id=approval_id)
    _assert_can_decide(subject, request)
    cached = store.get(tenant_id=tenant_id, idempotency_key=idempotency_key)
    if cached is not None:
        if cached.request_fingerprint != fingerprint:
            raise IdempotencyConflictError(
                f"idempotency key {idempotency_key!r} already bound to another request"
            )
        return dict(cached.response)

    try:
        updated = backend.approvals.revoke_request(
            tenant_id=tenant_id,
            run_id=request.run_id,
            request_id=request.request_id,
            decision_actor=subject.actor_id,
            decision_note=rationale,
        )
    except RequestAlreadyConsumedError as exc:
        updated = backend.approvals.load_request(
            tenant_id=tenant_id,
            run_id=request.run_id,
            request_id=request.request_id,
        )
        if updated.status != "revoked":
            raise ApprovalForbiddenError(str(exc)) from exc

    ensure_approval_resume_enqueued(
        backend,
        tenant_id=tenant_id,
        request=updated,
        decision="revoked",
    )
    response = {"approval_id": updated.request_id, "status": updated.status}
    store.save(
        ApprovalIdempotencyRecord(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            operation="revoke",
            request_fingerprint=fingerprint,
            response=response,
            created_at=updated.decision_at or "",
        )
    )
    if cached is None:
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
    return response
