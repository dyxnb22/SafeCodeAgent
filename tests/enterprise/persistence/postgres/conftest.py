"""PostgreSQL integration fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from psycopg import connect

from safecode.enterprise.persistence.postgres.backend import PostgresBackend
from safecode.enterprise.persistence.postgres.migrate import reset_schema_for_tests


def integration_dsn() -> str | None:
    return os.environ.get(
        "SAC_ENTERPRISE_TEST_DATABASE_URL",
        os.environ.get("SAC_ENTERPRISE_DATABASE_URL"),
    )


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
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
    with connect(postgres_dsn) as conn:
        reset_schema_for_tests(conn)
    backend = PostgresBackend.connect(postgres_dsn, tmp_path / ".sac")
    try:
        yield backend
    finally:
        backend.close()
