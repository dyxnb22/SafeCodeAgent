"""Offline deterministic vector store tests (v2.4.1-T1)."""

from __future__ import annotations

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.rag.vector_store import InMemoryKnowledgeVectorStore


def _chunk(
    *,
    chunk_id: str,
    tenant_id: str = "tenant-a",
    text: str,
    source_id: str = "policy-secure-sql-001",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id=source_id,
        tenant_id=tenant_id,
        path=f"{source_id}.md",
        start_line=1,
        end_line=3,
        source_type=SourceType.security_policy,
        permission_scope=["org", "appsec"],
        freshness="current",
        text=text,
        hash=f"sha256:{chunk_id}",
    )


def test_in_memory_store_returns_semantic_scores_for_same_tenant():
    store = InMemoryKnowledgeVectorStore()
    chunks = [
        _chunk(chunk_id="a", text="parameterized sql queries prevent injection"),
        _chunk(chunk_id="b", text="rotate credentials after secret leak"),
    ]
    store.upsert_chunks("tenant-a", chunks)
    scores = store.semantic_scores("tenant-a", "sql injection parameterized", ["a", "b"])
    assert scores["a"] >= scores["b"]


def test_cross_tenant_semantic_scores_are_empty():
    store = InMemoryKnowledgeVectorStore()
    store.upsert_chunks("tenant-a", [_chunk(chunk_id="a", text="tenant a policy")])
    scores = store.semantic_scores("tenant-b", "policy", ["a"])
    assert scores == {}


def test_hybrid_retriever_from_vector_store_matches_in_memory_contract():
    store = InMemoryKnowledgeVectorStore()
    store.upsert_chunks(
        "tenant-a",
        [
            _chunk(chunk_id="a", text="parameterized sql queries"),
            _chunk(chunk_id="b", text="secret rotation runbook", source_id="runbook-secret-leak"),
        ],
    )
    retriever = HybridRetriever.from_vector_store(store, "tenant-a")
    citations = retriever.retrieve("sql injection parameterized", k=2, actor_scope=["org", "appsec"])
    assert citations
    assert citations[0].source_id == "policy-secure-sql-001"
    assert citations[0].tenant_id == "tenant-a"


def test_cross_tenant_retrieval_from_vector_store_is_denied():
    store = InMemoryKnowledgeVectorStore()
    store.upsert_chunks("tenant-a", [_chunk(chunk_id="a", text="tenant a only")])
    retriever = HybridRetriever.from_vector_store(store, "tenant-a")
    citations = retriever.retrieve(
        "tenant a only",
        k=1,
        actor_scope=["org"],
        actor_tenant="tenant-b",
    )
    assert citations == []
