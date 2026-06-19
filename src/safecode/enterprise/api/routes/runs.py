"""Run read endpoints (v2.1.4-T2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from safecode.enterprise.api.read_service import (
    get_run,
    list_runs,
    run_detail_payload,
)
from safecode.enterprise.api.routes._deps import get_backend, require_tenant

router = APIRouter(prefix="/v2/runs", tags=["runs"])


@router.get("")
def list_runs_endpoint(
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
) -> dict[str, object]:
    items, next_cursor = list_runs(
        backend,
        tenant_id=tenant_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    payload: dict[str, object] = {
        "items": [
            {
                "run_id": item.run_id,
                "tenant_id": item.tenant_id,
                "task_type": item.task_type,
                "status": item.status,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in items
        ]
    }
    if next_cursor:
        payload["next_cursor"] = next_cursor
    return payload


@router.get("/{run_id}")
def get_run_endpoint(
    run_id: str,
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
) -> dict[str, str]:
    summary = get_run(backend, tenant_id=tenant_id, run_id=run_id)
    return run_detail_payload(summary, tenant_id=tenant_id)
