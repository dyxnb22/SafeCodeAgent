"""Pluggable embedding backends (v6.3.0).

The default backend tries to use sentence-transformers.
If not installed, falls back to NullEmbeddingBackend (keyword-only mode).

All backends return vectors of the same dimension so the store stays
schema-compatible regardless of which backend is active.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod

_NULL_DIM = 384    # matches all-MiniLM-L6-v2; chosen so null vectors are same size
_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_fallback_warning_emitted = False


class EmbeddingBackend(ABC):
    """Abstract embedding backend."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text."""

    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier for this backend/model."""

    @property
    def dimension(self) -> int:
        return _NULL_DIM

    @property
    def is_semantic(self) -> bool:
        """True only for real embedding backends; False for the null backend."""
        return False


class NullEmbeddingBackend(EmbeddingBackend):
    """Zero-vector backend used when no embedding library is available.

    The index builds and queries work; semantic scoring always returns 0.
    The system degrades gracefully to keyword-only retrieval.
    """

    install_hint = "pip install 'safecode-agent[semantic]' or pip install sentence-transformers"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * _NULL_DIM for _ in texts]

    def model_id(self) -> str:
        return "null"


class SentenceTransformerBackend(EmbeddingBackend):
    """Real semantic embeddings via sentence-transformers."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        self._model = SentenceTransformer(model_name)
        self._model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]

    def model_id(self) -> str:
        return self._model_name

    @property
    def is_semantic(self) -> bool:
        return True


def create_embedding_backend(model_name: str = _DEFAULT_MODEL) -> EmbeddingBackend:
    """Return a SentenceTransformerBackend if available, else NullEmbeddingBackend."""
    global _fallback_warning_emitted
    try:
        return SentenceTransformerBackend(model_name)
    except Exception:
        if not _fallback_warning_emitted:
            warnings.warn(NullEmbeddingBackend.install_hint, UserWarning, stacklevel=2)
            _fallback_warning_emitted = True
        return NullEmbeddingBackend()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. Returns 0.0 for zero vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
