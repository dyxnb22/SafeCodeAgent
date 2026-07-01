"""Semantic scorer wrapping the legacy embedding backend.

中文模块说明：RAG 语义打分支路，封装 kernel embedding 后端（可选依赖）。
- 架构位置：``retriever.py`` 混合检索的第二路打分。
- 安全不变量：离线测试可不装语义依赖；无 embedding 时优雅降级到 lexical。
- 学习路径：对照 ``lexical.py`` 与 ``test_vector_store_offline.py``。
"""

from __future__ import annotations

import hashlib
import math

from safecode.enterprise.rag.models import Chunk
from safecode.index.embedding_backend import EmbeddingBackend, NullEmbeddingBackend


class DeterministicEmbeddingBackend(EmbeddingBackend):
    """Hash-derived vectors for deterministic unit tests."""

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def model_id(self) -> str:
        return "deterministic-hash"

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def is_semantic(self) -> bool:
        return True

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self._dimension:
            for byte in digest:
                values.append((byte / 255.0) * 2 - 1)
                if len(values) >= self._dimension:
                    break
            digest = hashlib.sha256(digest).digest()
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def score_chunks(
    query: str,
    chunks: list[Chunk],
    backend: EmbeddingBackend | None = None,
) -> dict[str, float]:
    """Return semantic scores keyed by chunk_id."""
    embedder = backend or NullEmbeddingBackend()
    if not chunks:
        return {}
    texts = [chunk.text for chunk in chunks]
    vectors = embedder.embed([query, *texts])
    query_vector = vectors[0]
    scores: dict[str, float] = {}
    for chunk, vector in zip(chunks, vectors[1:]):
        if embedder.is_semantic:
            scores[chunk.chunk_id] = max(_cosine(query_vector, vector), 0.0)
        else:
            scores[chunk.chunk_id] = 0.0
    max_score = max(scores.values()) if scores else 1.0
    if max_score <= 0:
        return scores
    return {chunk_id: value / max_score for chunk_id, value in scores.items()}
