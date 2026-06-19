"""PostgreSQL schema and migration tests (v2.1.3-T1)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from psycopg import connect
from psycopg_pool import ConnectionPool

from safecode.enterprise.persistence.postgres.migrate import (
    SCHEMA_SQL,
    apply_migrations,
    apply_migrations_conn,
    list_migration_files,
    reset_schema_for_tests,
)

_OWNED_TABLES = (
    "checkpoints",
    "approval_requests",
    "grants",
    "audit_events",
    "eval_results",
    "evidence_index",
    "trace_events",
    "run_commands",
    "queue",
    "run_leases",
    "webhook_events",
    "knowledge_chunks",
    "knowledge_vectors",
    "memory_facts",
)


def _ddl_body(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def test_schema_snapshot_matches_migration_bundle() -> None:
    migration_sql = "".join(path.read_text(encoding="utf-8") for _, path in list_migration_files())
    canonical = SCHEMA_SQL.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS enterprise" in canonical
    assert _ddl_body(canonical) == _ddl_body(migration_sql)


@pytest.mark.parametrize("table_name", _OWNED_TABLES)
def test_owned_tables_require_tenant_id(table_name: str) -> None:
    ddl = SCHEMA_SQL.read_text(encoding="utf-8")
    pattern = rf"CREATE TABLE IF NOT EXISTS enterprise\.{table_name}\s*\((.*?)\n\);"
    match = re.search(pattern, ddl, flags=re.DOTALL)
    assert match is not None, f"missing table definition for {table_name}"
    body = match.group(1)
    assert "tenant_id TEXT NOT NULL" in body
    assert f"{table_name}_tenant_id_not_blank" in body


def test_migration_files_are_deterministic() -> None:
    first = list_migration_files()
    second = list_migration_files()
    assert first == second
    assert first[0][0] == "001_initial.sql"


def _integration_dsn() -> str:
    return os.environ.get(
        "SAC_ENTERPRISE_TEST_DATABASE_URL",
        os.environ.get(
            "SAC_ENTERPRISE_DATABASE_URL",
            "postgresql://safecode:safecode_test@127.0.0.1:5432/safecode_enterprise_test",
        ),
    )


@pytest.mark.postgres_integration
def test_migrations_apply_idempotently_to_real_postgres() -> None:
    dsn = _integration_dsn()
    try:
        with connect(dsn) as conn:
            reset_schema_for_tests(conn)
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {exc}")

    pool = ConnectionPool(dsn, min_size=1, max_size=2, open=True)
    try:
        apply_migrations(pool)
        apply_migrations(pool)
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT version FROM enterprise.schema_migrations ORDER BY version ASC"
            ).fetchall()
            tables = conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'enterprise'
                ORDER BY table_name ASC
                """
            ).fetchall()
    finally:
        pool.close()

    assert [row[0] for row in rows] == [version for version, _ in list_migration_files()]
    table_names = {row[0] for row in tables}
    for table_name in _OWNED_TABLES:
        assert table_name in table_names
