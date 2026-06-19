"""Deterministic reranker for hybrid retrieval (v2.4.3)."""

from __future__ import annotations

from dataclasses import dataclass

from safecode.enterprise.rag.models import Chunk


@dataclass(frozen=True)
class RerankCandidate:
    chunk: Chunk
    base_score: float
    lexical_score: float
    semantic_score: float


def rerank_candidates(
    candidates: list[RerankCandidate],
    *,
    lexical_boost: float = 0.15,
    exact_match_boost: float = 0.1,
    query_terms: set[str] | None = None,
) -> list[RerankCandidate]:
    """Deterministically rerank without live model calls."""
    terms = query_terms or set()

    def final_score(item: RerankCandidate) -> float:
        score = item.base_score
        score += lexical_boost * item.lexical_score
        if terms:
            lowered = item.chunk.text.lower()
            hits = sum(1 for term in terms if term in lowered)
            if hits:
                score += exact_match_boost * (hits / len(terms))
        return score

    return sorted(
        candidates,
        key=lambda item: (
            -final_score(item),
            item.chunk.path,
            item.chunk.start_line,
            item.chunk.chunk_id,
        ),
    )


def query_terms(query: str) -> set[str]:
    return {token for token in query.lower().split() if len(token) > 2}
