"""Permission filter tests for enterprise retrieval (v1.1.3-T3)."""

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType


def _chunk(source_id: str, scope: list[str], tenant: str = "local") -> Chunk:
    return Chunk(
        chunk_id=f"chunk-{source_id}",
        source_id=source_id,
        tenant_id=tenant,
        path=f"{source_id}.md",
        start_line=1,
        end_line=2,
        source_type=SourceType.security_policy,
        permission_scope=scope,
        freshness="current",
        text=f"content for {source_id}",
        hash=f"sha256:{source_id}",
    )


def test_permission_filter_runs_before_scoring():
    chunks = [
        _chunk("allowed", ["org"]),
        _chunk("restricted", ["org", "secops"]),
    ]
    retriever = HybridRetriever(chunks=chunks)
    citations = retriever.retrieve("content", k=5, actor_scope=["org"])
    assert [item.source_id for item in citations] == ["allowed"]
    assert any(event["type"] == "retrieval.permission_denied" for event in retriever.denied_events)


def test_tenant_mismatch_is_silent_and_excluded():
    chunks = [_chunk("tenant-a-doc", ["org"], tenant="tenant-a")]
    retriever = HybridRetriever(chunks=chunks)
    citations = retriever.retrieve("content", k=1, actor_scope=["org"], actor_tenant="tenant-b")
    assert citations == []
