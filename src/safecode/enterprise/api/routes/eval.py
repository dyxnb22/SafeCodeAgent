"""Eval baseline read endpoint (v2.1.4-T2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from safecode.enterprise.api.app import AppState
from safecode.enterprise.api.read_service import list_eval_baselines
from safecode.enterprise.api.routes._deps import get_app_state, require_tenant

router = APIRouter(prefix="/v2/eval", tags=["eval"])


@router.get("/baselines")
def list_eval_baselines_endpoint(
    tenant_id: Annotated[str, Depends(require_tenant)],
    state: Annotated[AppState, Depends(get_app_state)],
) -> dict[str, object]:
    _ = tenant_id
    return {"items": list_eval_baselines(state.eval_baselines_root)}
