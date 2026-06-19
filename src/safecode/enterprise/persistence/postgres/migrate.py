"""Forward-only idempotent PostgreSQL migrations for Enterprise persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
SCHEMA_SQL = Path(__file__).resolve().parent / "schema.sql"


def list_migration_files() -> list[tuple[str, Path]]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [(path.name, path) for path in files]


def apply_migrations_conn(conn: Any) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS enterprise")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS enterprise.schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for version, path in list_migration_files():
        exists = conn.execute(
            "SELECT 1 FROM enterprise.schema_migrations WHERE version = %s",
            (version,),
        ).fetchone()
        if exists:
            continue
        conn.execute(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO enterprise.schema_migrations (version) VALUES (%s)",
            (version,),
        )
    conn.commit()


def apply_migrations(pool: Any) -> None:
    with pool.connection() as conn:
        apply_migrations_conn(conn)


def reset_schema_for_tests(conn: Any) -> None:
    """Drop enterprise-owned objects for isolated integration tests."""
    conn.execute("DROP SCHEMA IF EXISTS enterprise CASCADE")
    conn.commit()
    apply_migrations_conn(conn)
