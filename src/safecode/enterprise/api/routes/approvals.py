"""Approval read and command endpoints (v2.1.4-T2, v2.1.5-T2)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.api.approval_service import decide_approval, revoke_approval_grant
from safecode.enterprise.api.read_service import approval_summary_payload, list_approvals
from safecode.enterprise.api.routes._deps import (
    get_backend,
    get_subject,
    require_idempotency_key,
    require_tenant,
    require_tenant_header,
)
from safecode.enterprise.rbac.models import RBACSubject

router = APIRouter(prefix="/v2/approvals", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    rationale: str = Field(default="", max_length=512)


@router.get("")
def list_approvals_endpoint(
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
    status: str | None = Query(default=None),
) -> dict[str, object]:
    items = list_approvals(backend, tenant_id=tenant_id, status=status)
    return {"items": [approval_summary_payload(item) for item in items]}


@router.post("/{approval_id}/decide")
def decide_approval_endpoint(
    approval_id: str,
    body: ApprovalDecisionRequest,
    tenant_id: Annotated[str, Depends(require_tenant_header)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    backend: Annotated[object, Depends(get_backend)],
    subject: Annotated[RBACSubject, Depends(get_subject)],
) -> dict[str, str]:
    return decide_approval(
        backend,
        tenant_id=tenant_id,
        approval_id=approval_id,
        subject=subject,
        decision=body.decision,
        rationale=body.rationale,
        idempotency_key=idempotency_key,
    )


@router.post("/{approval_id}/revoke")
def revoke_approval_endpoint(
    approval_id: str,
    tenant_id: Annotated[str, Depends(require_tenant_header)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    backend: Annotated[object, Depends(get_backend)],
    subject: Annotated[RBACSubject, Depends(get_subject)],
) -> dict[str, str]:
    return revoke_approval_grant(
        backend,
        tenant_id=tenant_id,
        approval_id=approval_id,
        subject=subject,
        rationale="",
        idempotency_key=idempotency_key,
    )
