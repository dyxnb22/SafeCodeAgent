"""PostgreSQL persistence package (v2.1.3)."""

from safecode.enterprise.persistence.postgres.migrate import apply_migrations

__all__ = ["apply_migrations"]
