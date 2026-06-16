"""Hybrid context retrieval combining keyword, semantic, and git-recency signals (v6.3.1).

Pipeline:
  1. Keyword score   — path-token matching (always available)
  2. Semantic score  — embedding cosine similarity (optional; 0 when null backend)
  3. Git-recency     — bonus for recently modified files (already in ContextSelector)

Every result carries a `selection_reason` explaining which signals fired.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.context.selector import ContextSelector, SelectedContextSource
from safecode.index.files import FileIndexer

_SEMANTIC_WEIGHT = 0.4   # weight applied to semantic score in [0,1]
_KEYWORD_WEIGHT  = 0.6   # weight applied to keyword score (normalized to [0,1])
_SEMANTIC_THRESHOLD = 0.25   # minimum cosine similarity to be considered a semantic match


@dataclass(frozen=True)
class HybridResult:
    """One result from hybrid retrieval with decomposed scoring."""

    path: str
    keyword_score: float
    semantic_score: float
    combined_score: float
    selection_reason: str  # human-readable explanation


class HybridRetriever:
    """Combines keyword + semantic + recency signals.

    Falls back gracefully to keyword-only when no embedding index exists
    or when the null backend is active.
    """

    def __init__(self, project_root: Path, sac_dir: Path | None = None) -> None:
        self.project_root = project_root
        self.sac_dir = sac_dir or (project_root / ".sac")
        self._selector = ContextSelector(project_root)

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        *,
        semantic_weight: float = _SEMANTIC_WEIGHT,
    ) -> list[HybridResult]:
        """Return ranked results; reason field describes which signals fired."""
        # Step 1: keyword sources (always present)
        keyword_sources = self._selector.select_sources(query, limit=limit * 3)
        keyword_map: dict[str, SelectedContextSource] = {s.path: s for s in keyword_sources}

        # Step 2: semantic sources (may be empty if no index or null backend)
        semantic_map = self._semantic_scores(query, limit=limit * 3)

        # Step 3: merge
        all_paths: set[str] = set(keyword_map) | set(semantic_map)
        max_keyword = max((s.score for s in keyword_sources), default=1) or 1

        results: list[HybridResult] = []
        for path in all_paths:
            kw_src = keyword_map.get(path)
            kw_score = (kw_src.score / max_keyword) if kw_src else 0.0
            sem_score = semantic_map.get(path, 0.0)

            combined = (1 - semantic_weight) * kw_score + semantic_weight * sem_score

            reasons: list[str] = []
            if kw_src and kw_score > 0:
                reasons.append(kw_src.reason)
            if sem_score >= _SEMANTIC_THRESHOLD:
                reasons.append(f"semantic ({sem_score:.2f})")

            selection_reason = "; ".join(reasons) if reasons else "recency"

            results.append(HybridResult(
                path=path,
                keyword_score=round(kw_score, 3),
                semantic_score=round(sem_score, 3),
                combined_score=round(combined, 3),
                selection_reason=selection_reason,
            ))

        results.sort(key=lambda r: -r.combined_score)
        return results[:limit]

    def _semantic_scores(self, query: str, limit: int) -> dict[str, float]:
        """Return {file_path: cosine_score} from embedding store. Empty if unavailable."""
        try:
            from safecode.index.embedding_store import EmbeddingStore
            store = EmbeddingStore(self.sac_dir)
            hits = store.search(query, limit=limit)
            return {h.file_path: h.score for h in hits}
        except Exception:
            return {}
