"""Knowledge vector store protocol and deterministic offline harness (v2.4.1)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.semantic import DeterministicEmbeddingBackend
from safecode.index.embedding_backend import EmbeddingBackend

DEFAULT_VECTOR_DIMENSION = 384


def vector_literal(values: list[float]) -> str:
    """Format a float vector for PostgreSQL pgvector casts."""
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return scores
    return {chunk_id: value / max_score for chunk_id, value in scores.items()}


@runtime_checkable
class KnowledgeVectorStore(Protocol):
    """Tenant-scoped chunk and embedding persistence for hybrid retrieval."""

    def upsert_chunks(
        self,
        tenant_id: str,
        chunks: list[Chunk],
        *,
        backend: EmbeddingBackend | None = None,
    ) -> int: ...

    def list_chunks(self, tenant_id: str) -> list[Chunk]: ...

    def semantic_scores(
        self,
        tenant_id: str,
        query: str,
        chunk_ids: list[str],
        *,
        backend: EmbeddingBackend | None = None,
    ) -> dict[str, float]: ...


@dataclass
class InMemoryKnowledgeVectorStore:
    """Deterministic offline store mirroring the pgvector contract."""

    dimension: int = DEFAULT_VECTOR_DIMENSION
    _chunks: dict[tuple[str, str], Chunk] = field(default_factory=dict)
    _vectors: dict[tuple[str, str, str], list[float]] = field(default_factory=dict)

    def upsert_chunks(
        self,
        tenant_id: str,
        chunks: list[Chunk],
        *,
        backend: EmbeddingBackend | None = None,
    ) -> int:
        embedder = backend or DeterministicEmbeddingBackend(dimension=self.dimension)
        if not chunks:
            return 0
        texts = [chunk.text for chunk in chunks]
        vectors = embedder.embed(texts)
        model_id = embedder.model_id()
        written = 0
        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.dimension:
                raise ValueError(f"embedding dimension mismatch: expected {self.dimension}")
            key = (tenant_id, chunk.chunk_id)
            self._chunks[key] = chunk.model_copy(update={"tenant_id": tenant_id})
            self._vectors[(tenant_id, chunk.chunk_id, model_id)] = vector
            written += 1
        return written

    def list_chunks(self, tenant_id: str) -> list[Chunk]:
        items = [chunk for (tenant, _), chunk in self._chunks.items() if tenant == tenant_id]
        return sorted(items, key=lambda chunk: (chunk.source_id, chunk.path, chunk.start_line, chunk.chunk_id))

    def semantic_scores(
        self,
        tenant_id: str,
        query: str,
        chunk_ids: list[str],
        *,
        backend: EmbeddingBackend | None = None,
    ) -> dict[str, float]:
        embedder = backend or DeterministicEmbeddingBackend(dimension=self.dimension)
        if not chunk_ids:
            return {}
        query_vector = embedder.embed([query])[0]
        model_id = embedder.model_id()
        scores: dict[str, float] = {}
        for chunk_id in chunk_ids:
            vector = self._vectors.get((tenant_id, chunk_id, model_id))
            if vector is None:
                continue
            scores[chunk_id] = max(_cosine(query_vector, vector), 0.0)
        return normalize_scores(scores)


def chunk_to_row(chunk: Chunk) -> dict[str, object]:
    return {
        "tenant_id": chunk.tenant_id,
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "path": chunk.path,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "source_type": chunk.source_type.value,
        "permission_scope": json.dumps(chunk.permission_scope),
        "freshness": chunk.freshness,
        "content_hash": chunk.hash,
        "chunk_text": chunk.text,
        "metadata": json.dumps(chunk.metadata),
    }


def row_to_chunk(row: tuple[object, ...]) -> Chunk:
    from safecode.enterprise.rag.source_registry import SourceType

    permission_scope = row[7]
    metadata = row[11]
    if isinstance(permission_scope, str):
        permission_scope = json.loads(permission_scope)
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return Chunk(
        chunk_id=str(row[1]),
        source_id=str(row[2]),
        tenant_id=str(row[0]),
        path=str(row[3]),
        start_line=int(row[4]),
        end_line=int(row[5]),
        source_type=SourceType(str(row[6])),
        permission_scope=list(permission_scope),
        freshness=str(row[8]),  # type: ignore[arg-type]
        text=str(row[10]),
        hash=str(row[9]),
        metadata=dict(metadata),
    )


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
