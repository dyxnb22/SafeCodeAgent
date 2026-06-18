"""Tests for lexical scorer (v1.1.3-T1)."""

from safecode.enterprise.rag.lexical import score_chunks
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.source_registry import SourceType


def _chunk(text: str, chunk_id: str = "chunk-1") -> Chunk:
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
        hash="sha256:abc",
    )


def test_lexical_scoring_is_deterministic():
    chunks = [
        _chunk("Always use parameterized SQL queries.", "chunk-a"),
        _chunk("Rotate credentials after a secret leak.", "chunk-b"),
    ]
    first = score_chunks("sql injection parameterized", chunks)
    second = score_chunks("sql injection parameterized", chunks)
    assert first == second
    assert first["chunk-a"] > first["chunk-b"]
