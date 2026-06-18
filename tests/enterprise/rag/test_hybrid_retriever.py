"""Tests for HybridRetriever (v1.1.3-T3)."""

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType


def _chunk(source_id: str, text: str, scope: list[str], chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id=source_id,
        path=f"{source_id}.md",
        start_line=1,
        end_line=3,
        source_type=SourceType.security_policy,
        permission_scope=scope,
        freshness="current",
        text=text,
        hash=f"sha256:{chunk_id}",
    )


def test_retriever_returns_sorted_citations_with_scores():
    chunks = [
        _chunk("policy-secure-sql-001", "parameterized sql queries", ["org", "appsec"], "chunk-a"),
        _chunk("runbook-secret-leak", "rotate credentials after leak", ["org", "secops"], "chunk-b"),
    ]
    retriever = HybridRetriever(chunks=chunks)
    citations = retriever.retrieve("sql injection parameterized", k=2, actor_scope=["org", "appsec"])
    assert citations
    assert citations[0].source_id == "policy-secure-sql-001"
    assert citations[0].score >= citations[-1].score
    assert citations[0].citation_id
    assert citations[0].selection_reason.startswith("lex=")


def test_retriever_is_deterministic_for_identical_queries():
    chunks = [_chunk("policy-secure-sql-001", "parameterized sql queries", ["org"], "chunk-a")]
    retriever = HybridRetriever(chunks=chunks)
    first = retriever.retrieve("sql injection", k=1, actor_scope=["org"])
    second = retriever.retrieve("sql injection", k=1, actor_scope=["org"])
    assert first[0].citation_id == second[0].citation_id
