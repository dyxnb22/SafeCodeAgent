"""Shared FastAPI route dependencies (v2.1.4-T2)."""

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
from safecode.enterprise.api.read_service import enforce_tenant_scope
from safecode.enterprise.api.settings import RuntimeMode
from safecode.enterprise.rbac.models import RBACSubject


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
) -> str:
    return enforce_tenant_scope(subject, tenant_id)


def require_tenant_header(
    x_tenant_id: Annotated[str, Header(alias="X-Tenant-Id")],
    subject: Annotated[RBACSubject, Depends(get_subject)],
) -> str:
    return enforce_tenant_scope(subject, x_tenant_id)


def require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if idempotency_key is None:
        raise IdempotencyKeyRequiredError("Idempotency-Key header is required")
    normalized = idempotency_key.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise IdempotencyKeyRequiredError("Idempotency-Key must be between 8 and 128 characters")
    return normalized
