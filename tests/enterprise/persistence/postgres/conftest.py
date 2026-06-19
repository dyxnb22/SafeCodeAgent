"""PostgreSQL integration fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    from psycopg import connect
except ImportError:  # pragma: no cover - exercised in the minimal dependency lane
    connect = None


DEFAULT_INTEGRATION_DSN = (
    "postgresql://safecode:safecode_test@127.0.0.1:5432/safecode_enterprise_test"
)


def integration_dsn() -> str | None:
    return os.environ.get(
        "SAC_ENTERPRISE_TEST_DATABASE_URL",
        os.environ.get("SAC_ENTERPRISE_DATABASE_URL"),
    ) or DEFAULT_INTEGRATION_DSN


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    if connect is None:
        pytest.skip("psycopg optional dependency is not installed")
    dsn = integration_dsn()
    if not dsn:
        pytest.skip("postgres integration DSN not configured")
    try:
        with connect(dsn) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {exc}")
    return dsn


@pytest.fixture
def postgres_backend(postgres_dsn: str, tmp_path: Path):
    from safecode.enterprise.persistence.postgres.backend import PostgresBackend
    from safecode.enterprise.persistence.postgres.migrate import reset_schema_for_tests

    assert connect is not None
    with connect(postgres_dsn) as conn:
        reset_schema_for_tests(conn)
    backend = PostgresBackend.connect(postgres_dsn, tmp_path / ".sac")
    try:
        yield backend
    finally:
        backend.close()
