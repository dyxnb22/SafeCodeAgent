"""Tenant identifier validation shared by all Enterprise layers."""

from __future__ import annotations

import re


class MissingTenantIdError(ValueError):
    """Raised when an Enterprise operation lacks a safe tenant identifier."""

_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_tenant_id(tenant_id: str | None) -> str:
    """Return a canonical tenant identifier safe for SQL and local paths."""
    if tenant_id is None:
        raise MissingTenantIdError("tenant_id is required")
    normalized = tenant_id.strip()
    if not normalized:
        raise MissingTenantIdError("tenant_id is required")
    if normalized in {".", ".."} or not _TENANT_ID_RE.fullmatch(normalized):
        raise MissingTenantIdError(
            "tenant_id must be 1-128 path-safe ASCII characters and start with an alphanumeric"
        )
    return normalized
