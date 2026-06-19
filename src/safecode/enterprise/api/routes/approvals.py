"""Approval read endpoints (v2.1.4-T2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from safecode.enterprise.api.read_service import approval_summary_payload, list_approvals
from safecode.enterprise.api.routes._deps import get_backend, require_tenant

router = APIRouter(prefix="/v2/approvals", tags=["approvals"])


@router.get("")
def list_approvals_endpoint(
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
    status: str | None = Query(default=None),
) -> dict[str, object]:
    items = list_approvals(backend, tenant_id=tenant_id, status=status)
    return {"items": [approval_summary_payload(item) for item in items]}
