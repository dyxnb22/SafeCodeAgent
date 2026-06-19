"""Evidence export read endpoint (v2.1.4-T2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from safecode.enterprise.api.routes._deps import get_backend, require_tenant

router = APIRouter(prefix="/v2/evidence", tags=["evidence"])


@router.get("/{run_id}")
def export_evidence_endpoint(
    run_id: str,
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
) -> FileResponse:
    zip_path = backend.evidence.export_run_evidence(tenant_id=tenant_id, run_id=run_id)
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"evidence-{run_id}.zip",
    )
