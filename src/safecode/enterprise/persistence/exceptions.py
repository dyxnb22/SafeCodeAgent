"""Persistence layer exceptions."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base persistence error."""


class MissingTenantIdError(PersistenceError):
    """Raised when a persistence operation lacks a tenant_id."""


class TenantBoundaryError(PersistenceError):
    """Raised when a tenant-scoped read or write crosses tenant boundaries."""
