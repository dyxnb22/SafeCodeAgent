"""Retrieval tenant filter tests."""

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType


def _chunk(tenant_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"chunk-{tenant_id}",
        source_id=f"policy-{tenant_id}",
        path="policy.md",
        start_line=1,
        end_line=2,
        source_type=SourceType.security_policy,
        tenant_id=tenant_id,
        permission_scope=["org"],
        freshness="current",
        text=text,
        hash=f"sha256:{tenant_id}",
    )


def test_tenant_a_never_retrieves_tenant_b_chunks():
    shared_text = "parameterized SQL queries prevent injection"
    retriever = HybridRetriever(
        chunks=[
            _chunk("tenant-a", shared_text),
            _chunk("tenant-b", shared_text),
        ]
    )
    results = retriever.retrieve(
        "sql injection policy",
        k=5,
        actor_scope=["org"],
        actor_tenant="tenant-a",
    )
    assert results
    assert all(item.tenant_id == "tenant-a" for item in results)
    assert not any(item.tenant_id == "tenant-b" for item in results)


def test_cross_tenant_query_returns_empty_when_only_other_tenant_indexed():
    retriever = HybridRetriever(chunks=[_chunk("tenant-b", "secure sql guidance")])
    results = retriever.retrieve(
        "secure sql",
        k=5,
        actor_scope=["org"],
        actor_tenant="tenant-a",
    )
    assert results == []
