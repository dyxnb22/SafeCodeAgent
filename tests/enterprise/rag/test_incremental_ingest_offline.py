"""Incremental ingest tests (v2.4.2-T1)."""

from __future__ import annotations

import pytest

from safecode.enterprise.rag.exceptions import AclSyncError
from safecode.enterprise.rag.incremental_ingest import IncrementalIngestor
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.rag.vector_store import InMemoryKnowledgeVectorStore, KnowledgeVectorStore


def _chunk(
    chunk_id: str,
    text: str,
    *,
    scope: list[str] | None = None,
    source_id: str = "policy-secure-sql-001",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id=source_id,
        tenant_id="tenant-a",
        path="policy.md",
        start_line=1,
        end_line=3,
        source_type=SourceType.security_policy,
        permission_scope=scope or ["org", "appsec"],
        freshness="current",
        text=text,
        hash=f"sha256:{chunk_id}-{len(text)}",
    )


def test_reingest_unchanged_source_is_no_op():
    store = InMemoryKnowledgeVectorStore()
    ingestor = IncrementalIngestor(store=store)
    chunks = [_chunk("a", "parameterized sql queries")]
    first = ingestor.ingest_source("tenant-a", "policy-secure-sql-001", chunks)
    second = ingestor.ingest_source("tenant-a", "policy-secure-sql-001", chunks)
    assert first.inserted == 1
    assert second.skipped == 1
    assert second.updated == 0


def test_acl_change_propagates_before_next_retrieval():
    store = InMemoryKnowledgeVectorStore()
    ingestor = IncrementalIngestor(store=store)
    original = [_chunk("a", "parameterized sql queries", scope=["org", "secops"])]
    ingestor.ingest_source("tenant-a", "policy-secure-sql-001", original)
    retriever = HybridRetriever.from_vector_store(store, "tenant-a")
    denied = retriever.retrieve("sql", k=1, actor_scope=["org", "appsec"])
    assert denied == []

    updated = [_chunk("a", "parameterized sql queries", scope=["org", "appsec"])]
    report = ingestor.ingest_source("tenant-a", "policy-secure-sql-001", updated)
    assert report.acl_updated == 1
    allowed = retriever.retrieve("sql", k=1, actor_scope=["org", "appsec"])
    assert allowed


def test_removed_chunks_marked_superseded():
    store = InMemoryKnowledgeVectorStore()
    ingestor = IncrementalIngestor(store=store)
    ingestor.ingest_source(
        "tenant-a",
        "policy-secure-sql-001",
        [_chunk("a", "one"), _chunk("b", "two")],
    )
    ingestor.ingest_source("tenant-a", "policy-secure-sql-001", [_chunk("a", "one")])
    chunks = {chunk.chunk_id: chunk.freshness for chunk in store.list_chunks("tenant-a")}
    assert chunks["b"] == "superseded"


class _FailingAclStore(InMemoryKnowledgeVectorStore):
    def update_permission_scope(
        self, tenant_id: str, chunk_id: str, permission_scope: list[str]
    ) -> None:
        raise RuntimeError("acl backend unavailable")


def test_acl_sync_failure_fails_closed():
    store = _FailingAclStore()
    ingestor = IncrementalIngestor(store=store, fail_closed_on_acl_sync=True)
    ingestor.ingest_source("tenant-a", "policy-secure-sql-001", [_chunk("a", "baseline", scope=["org"])])
    with pytest.raises(AclSyncError):
        ingestor.ingest_source(
            "tenant-a",
            "policy-secure-sql-001",
            [_chunk("a", "baseline", scope=["org", "appsec"])],
        )
