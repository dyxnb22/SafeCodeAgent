"""Run read and command endpoints (v2.1.4-T2, v2.1.5-T1).

中文模块说明：``/v2/runs`` 读写面：列表/详情为只读，start/resume/cancel 为异步命令。
- 架构位置：Service 平面主入口；写操作委托 ``worker/commands.py``。
- 安全不变量：写路由要求 developer+ RBAC、``X-Tenant-Id``、``Idempotency-Key``。
- 学习路径：配合 ``read_service.py`` 与 ``test_run_commands.py`` 阅读。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.api.app import AppState
from safecode.enterprise.api.read_service import (
    get_run,
    list_runs,
    run_detail_payload,
)
from safecode.enterprise.api.routes._deps import (
    get_app_state,
    get_backend,
    get_subject,
    require_minimum_role,
    require_idempotency_key,
    require_tenant,
    require_tenant_header,
)
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.worker.commands import cancel_run, command_queue_for, resume_run, start_run
from safecode.enterprise.worker.models import RunAccepted

router = APIRouter(prefix="/v2/runs", tags=["runs"])


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str
    input_ref: str | None = Field(default=None, max_length=512)


def _accepted_response(accepted: RunAccepted) -> dict[str, str]:
    return {
        "run_id": accepted.run_id,
        "status": accepted.status,
        "status_url": accepted.status_url,
    }


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


def _project_root(state: AppState, backend: object) -> Path:
    if state.project_root is not None:
        return state.project_root
    if isinstance(backend, LocalBackend):
        return backend.sac_root.parent
    return backend.artifacts_root.parent  # type: ignore[attr-defined]


@router.post("", status_code=202)
def start_run_endpoint(
    body: StartRunRequest,
    response: Response,
    tenant_id: Annotated[str, Depends(require_tenant_header)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    backend: Annotated[object, Depends(get_backend)],
    subject: Annotated[RBACSubject, Depends(get_subject)],
    state: Annotated[AppState, Depends(get_app_state)],
) -> dict[str, str]:
    require_minimum_role(subject, Role.developer, action="start runs")
    state.rate_limiter.check_inflight(backend, tenant_id)
    queue = command_queue_for(backend)
    accepted = start_run(
        backend,
        queue,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        task_type=body.task_type,
        input_ref=body.input_ref,
        subject=subject,
        project_root=_project_root(state, backend),
    )
    response.status_code = 202
    return _accepted_response(accepted)


@router.get("/{run_id}")
def get_run_endpoint(
    run_id: str,
    tenant_id: Annotated[str, Depends(require_tenant)],
    backend: Annotated[object, Depends(get_backend)],
) -> dict[str, str]:
    summary = get_run(backend, tenant_id=tenant_id, run_id=run_id)
    return run_detail_payload(summary, tenant_id=tenant_id)


@router.post("/{run_id}/resume", status_code=202)
def resume_run_endpoint(
    run_id: str,
    response: Response,
    tenant_id: Annotated[str, Depends(require_tenant_header)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    backend: Annotated[object, Depends(get_backend)],
    subject: Annotated[RBACSubject, Depends(get_subject)],
) -> dict[str, str]:
    require_minimum_role(subject, Role.developer, action="resume runs")
    queue = command_queue_for(backend)
    accepted = resume_run(
        backend,
        queue,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        run_id=run_id,
    )
    response.status_code = 202
    return _accepted_response(accepted)


@router.post("/{run_id}/cancel", status_code=202)
def cancel_run_endpoint(
    run_id: str,
    response: Response,
    tenant_id: Annotated[str, Depends(require_tenant_header)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    backend: Annotated[object, Depends(get_backend)],
    subject: Annotated[RBACSubject, Depends(get_subject)],
) -> dict[str, str]:
    require_minimum_role(subject, Role.developer, action="cancel runs")
    queue = command_queue_for(backend)
    accepted = cancel_run(
        backend,
        queue,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        run_id=run_id,
    )
    response.status_code = 202
    return _accepted_response(accepted)
