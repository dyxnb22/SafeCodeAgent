"""Trace and timeline read endpoints (v2.1.4-T2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from safecode.enterprise.api.read_service import (
    build_run_timeline,
    list_redacted_trace_events,
    timeline_payload,
    trace_payload,
)
from safecode.enterprise.api.routes._deps import get_backend, require_tenant

router = APIRouter(prefix="/v2/runs", tags=["runs"])


@router.get("/{run_id}/timeline")
def get_run_timeline_endpoint(
    run_id: str,
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
) -> dict[str, object]:
    timeline = build_run_timeline(backend, tenant_id=tenant_id, run_id=run_id)
    return timeline_payload(timeline)


@router.get("/{run_id}/trace")
def get_run_trace_endpoint(
    run_id: str,
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
) -> dict[str, object]:
    events = list_redacted_trace_events(backend, tenant_id=tenant_id, run_id=run_id)
    return trace_payload(run_id, events)
