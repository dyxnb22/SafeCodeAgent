"""Lazy PostgreSQL persistence exports for the optional Team Server extra."""

from __future__ import annotations

from typing import Any

__all__ = ["PostgresBackend", "apply_migrations"]


def __getattr__(name: str) -> Any:
    if name == "PostgresBackend":
        from safecode.enterprise.persistence.postgres.backend import PostgresBackend

        return PostgresBackend
    if name == "apply_migrations":
        from safecode.enterprise.persistence.postgres.migrate import apply_migrations

        return apply_migrations
    raise AttributeError(name)
