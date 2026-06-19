"""Persistence layer exceptions."""

from __future__ import annotations

from safecode.enterprise.tenancy import MissingTenantIdError


class PersistenceError(Exception):
    """Base persistence error."""


class TenantBoundaryError(PersistenceError):
    """Raised when a tenant-scoped read or write crosses tenant boundaries."""
