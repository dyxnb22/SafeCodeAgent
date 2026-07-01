"""Shared FastAPI route dependencies (v2.1.4-T2).

中文模块说明：路由层 Depends 快捷方式：租户 header、RBAC 最低角色、幂等键。
- 架构位置：``routes/*`` 的统一门禁；封装 ``dependencies.py`` 的解析结果。
- 安全不变量：``require_minimum_role``；server 模式写操作强制 Idempotency-Key。
- 学习路径：打开任意 ``routes/*.py`` 看 Depends 列表即懂 API 门禁。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from safecode.enterprise.api.app import AppState
from safecode.enterprise.api.dependencies import (
    AuthenticationRequiredError,
    PersistenceBackend,
    resolve_bearer_subject,
    resolve_subject,
)
from safecode.enterprise.api.exceptions import IdempotencyKeyRequiredError
from safecode.enterprise.api.exceptions import ApprovalForbiddenError
from safecode.enterprise.api.read_service import enforce_tenant_scope
from safecode.enterprise.api.settings import RuntimeMode
from safecode.enterprise.rbac.models import RBACSubject, ROLE_RANK, Role


def get_app_state(request: Request) -> AppState:
    return request.app.state.enterprise


def get_backend(state: Annotated[AppState, Depends(get_app_state)]) -> PersistenceBackend:
    return state.backend


def get_subject(
    request: Request,
    state: Annotated[AppState, Depends(get_app_state)],
) -> RBACSubject:
    if state.settings.runtime_mode is RuntimeMode.LOCAL:
        return resolve_subject(state.subject_resolver)
    if state.oidc_validator is None:
        raise AuthenticationRequiredError("authenticated subject required")
    return resolve_bearer_subject(
        request.headers.get("Authorization"),
        oidc_validator=state.oidc_validator,
    )


def require_tenant(
    tenant_id: str,
    subject: Annotated[RBACSubject, Depends(get_subject)],
    state: Annotated[AppState, Depends(get_app_state)],
) -> str:
    tenant = enforce_tenant_scope(subject, tenant_id)
    state.rate_limiter.check_request(tenant)
    return tenant


def require_tenant_header(
    x_tenant_id: Annotated[str, Header(alias="X-Tenant-Id")],
    subject: Annotated[RBACSubject, Depends(get_subject)],
    state: Annotated[AppState, Depends(get_app_state)],
) -> str:
    tenant = enforce_tenant_scope(subject, x_tenant_id)
    state.rate_limiter.check_request(tenant)
    return tenant


def require_minimum_role(subject: RBACSubject, minimum: Role, *, action: str) -> None:
    if ROLE_RANK[subject.highest_role()] < ROLE_RANK[minimum]:
        raise ApprovalForbiddenError(
            f"role {subject.highest_role().value!r} cannot {action}; {minimum.value!r} required"
        )


def require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if idempotency_key is None:
        raise IdempotencyKeyRequiredError("Idempotency-Key header is required")
    normalized = idempotency_key.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise IdempotencyKeyRequiredError("Idempotency-Key must be between 8 and 128 characters")
    return normalized
