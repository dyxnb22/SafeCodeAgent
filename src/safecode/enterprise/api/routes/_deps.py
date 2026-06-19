"""Shared FastAPI route dependencies (v2.1.4-T2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from safecode.enterprise.api.app import AppState
from safecode.enterprise.api.dependencies import resolve_subject
from safecode.enterprise.api.read_service import PersistenceBackend, enforce_tenant_scope
from safecode.enterprise.rbac.models import RBACSubject


def get_app_state(request: Request) -> AppState:
    return request.app.state.enterprise


def get_backend(state: Annotated[AppState, Depends(get_app_state)]) -> PersistenceBackend:
    return state.backend


def get_subject(state: Annotated[AppState, Depends(get_app_state)]) -> RBACSubject:
    return resolve_subject(state.subject_resolver)


def require_tenant(
    tenant_id: str,
    subject: Annotated[RBACSubject, Depends(get_subject)],
) -> str:
    return enforce_tenant_scope(subject, tenant_id)
