"""Tests for semantic scorer (v1.1.3-T2)."""

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.semantic import DeterministicEmbeddingBackend, score_chunks
from safecode.enterprise.rag.source_registry import SourceType


def _chunk(text: str, chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id="policy-secure-sql-001",
        path="policy.md",
        start_line=1,
        end_line=3,
        source_type=SourceType.security_policy,
        permission_scope=["org"],
        freshness="current",
        text=text,
        hash=f"sha256:{chunk_id}",
    )


def test_semantic_scorer_returns_chunk_keyed_scores():
    backend = DeterministicEmbeddingBackend()
    chunks = [
        _chunk("parameterized sql queries", "chunk-a"),
        _chunk("secret leak runbook", "chunk-b"),
    ]
    scores = score_chunks("sql injection", chunks, backend=backend)
    assert set(scores) == {"chunk-a", "chunk-b"}
    first = score_chunks("sql injection", chunks, backend=backend)
    second = score_chunks("sql injection", chunks, backend=backend)
    assert first == second
