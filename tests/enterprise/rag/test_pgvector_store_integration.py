"""PostgreSQL pgvector integration tests (v2.4.1-T1)."""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from psycopg import connect

from safecode.enterprise.persistence.postgres.migrate import reset_schema_for_tests
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.pgvector_store import PgVectorKnowledgeStore
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType

DEFAULT_INTEGRATION_DSN = (
    "postgresql://safecode:safecode_test@127.0.0.1:5432/safecode_enterprise_test"
)


def integration_dsn() -> str | None:
    import os

    return os.environ.get(
        "SAC_ENTERPRISE_TEST_DATABASE_URL",
        os.environ.get("SAC_ENTERPRISE_DATABASE_URL"),
    ) or DEFAULT_INTEGRATION_DSN


def _chunk(chunk_id: str, text: str, tenant_id: str = "tenant-a") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id="policy-secure-sql-001",
        tenant_id=tenant_id,
        path="policy.md",
        start_line=1,
        end_line=3,
        source_type=SourceType.security_policy,
        permission_scope=["org", "appsec"],
        freshness="current",
        text=text,
        hash=f"sha256:{chunk_id}",
    )


@pytest.mark.postgres_integration
def test_pgvector_store_tenant_scoped_similarity_search():
    dsn = integration_dsn()
    if not dsn:
        pytest.skip("postgres integration DSN not configured")
    try:
        with connect(dsn) as conn:
            reset_schema_for_tests(conn)
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {exc}")

    store = PgVectorKnowledgeStore.connect(dsn)
    try:
        store.upsert_chunks(
            "tenant-a",
            [
                _chunk("a", "parameterized sql queries prevent injection"),
                _chunk("b", "rotate credentials after secret leak"),
            ],
        )
        store.upsert_chunks("tenant-b", [_chunk("x", "tenant b policy only", tenant_id="tenant-b")])
        scores = store.semantic_scores("tenant-a", "sql injection parameterized", ["a", "b"])
        assert scores["a"] >= scores["b"]
        cross = store.semantic_scores("tenant-b", "sql injection parameterized", ["a", "b"])
        assert cross == {}
        retriever = HybridRetriever.from_vector_store(store, "tenant-a")
        citations = retriever.retrieve("sql injection", k=1, actor_scope=["org", "appsec"])
        assert citations
        assert citations[0].source_id == "policy-secure-sql-001"
    finally:
        store.close()


@pytest.mark.postgres_integration
def test_pgvector_migrations_apply_idempotently():
    dsn = integration_dsn()
    if not dsn:
        pytest.skip("postgres integration DSN not configured")
    try:
        with connect(dsn) as conn:
            reset_schema_for_tests(conn)
            reset_schema_for_tests(conn)
            rows = conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'enterprise'
                  AND table_name IN ('knowledge_chunks', 'knowledge_vectors')
                ORDER BY table_name ASC
                """
            ).fetchall()
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {exc}")
    assert [row[0] for row in rows] == ["knowledge_chunks", "knowledge_vectors"]
