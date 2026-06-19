"""PostgreSQL pgvector-backed knowledge store (v2.4.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from psycopg import Connection
from psycopg_pool import ConnectionPool

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.semantic import DeterministicEmbeddingBackend
from safecode.enterprise.rag.vector_store import (
    DEFAULT_VECTOR_DIMENSION,
    chunk_to_row,
    normalize_scores,
    row_to_chunk,
    vector_literal,
)
from safecode.index.embedding_backend import EmbeddingBackend


@dataclass(frozen=True)
class PgVectorKnowledgeStore:
    """Tenant-scoped chunk and embedding persistence using pgvector."""

    pool: ConnectionPool
    dimension: int = DEFAULT_VECTOR_DIMENSION

    def upsert_chunks(
        self,
        tenant_id: str,
        chunks: list[Chunk],
        *,
        backend: EmbeddingBackend | None = None,
    ) -> int:
        tenant = validate_tenant_id(tenant_id)
        embedder = backend or DeterministicEmbeddingBackend(dimension=self.dimension)
        if not chunks:
            return 0
        texts = [chunk.text for chunk in chunks]
        vectors = embedder.embed(texts)
        model_id = embedder.model_id()
        written = 0
        with self.pool.connection() as conn:
            for chunk, vector in zip(chunks, vectors):
                if len(vector) != self.dimension:
                    raise ValueError(
                        f"embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                    )
                row = chunk_to_row(chunk.model_copy(update={"tenant_id": tenant}))
                conn.execute(
                    """
                    INSERT INTO enterprise.knowledge_chunks (
                        tenant_id, chunk_id, source_id, path, start_line, end_line,
                        source_type, permission_scope, freshness, content_hash,
                        chunk_text, metadata, updated_at
                    ) VALUES (
                        %(tenant_id)s, %(chunk_id)s, %(source_id)s, %(path)s,
                        %(start_line)s, %(end_line)s, %(source_type)s,
                        %(permission_scope)s::jsonb, %(freshness)s, %(content_hash)s,
                        %(chunk_text)s, %(metadata)s::jsonb, NOW()
                    )
                    ON CONFLICT (tenant_id, chunk_id) DO UPDATE SET
                        source_id = EXCLUDED.source_id,
                        path = EXCLUDED.path,
                        start_line = EXCLUDED.start_line,
                        end_line = EXCLUDED.end_line,
                        source_type = EXCLUDED.source_type,
                        permission_scope = EXCLUDED.permission_scope,
                        freshness = EXCLUDED.freshness,
                        content_hash = EXCLUDED.content_hash,
                        chunk_text = EXCLUDED.chunk_text,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    """,
                    row,
                )
                conn.execute(
                    """
                    INSERT INTO enterprise.knowledge_vectors (
                        tenant_id, chunk_id, model_id, embedding
                    ) VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (tenant_id, chunk_id, model_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding
                    """,
                    (tenant, chunk.chunk_id, model_id, vector_literal(vector)),
                )
                written += 1
            conn.commit()
        return written

    def list_chunks(self, tenant_id: str) -> list[Chunk]:
        tenant = validate_tenant_id(tenant_id)
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT tenant_id, chunk_id, source_id, path, start_line, end_line,
                       source_type, permission_scope, freshness, content_hash,
                       chunk_text, metadata
                FROM enterprise.knowledge_chunks
                WHERE tenant_id = %s
                ORDER BY source_id ASC, path ASC, start_line ASC, chunk_id ASC
                """,
                (tenant,),
            ).fetchall()
        return [row_to_chunk(row) for row in rows]

    def semantic_scores(
        self,
        tenant_id: str,
        query: str,
        chunk_ids: list[str],
        *,
        backend: EmbeddingBackend | None = None,
    ) -> dict[str, float]:
        tenant = validate_tenant_id(tenant_id)
        if not chunk_ids:
            return {}
        embedder = backend or DeterministicEmbeddingBackend(dimension=self.dimension)
        query_vector = embedder.embed([query])[0]
        model_id = embedder.model_id()
        literal = vector_literal(query_vector)
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT v.chunk_id,
                       1 - (v.embedding <=> %s::vector) AS cosine_similarity
                FROM enterprise.knowledge_vectors v
                WHERE v.tenant_id = %s
                  AND v.model_id = %s
                  AND v.chunk_id = ANY(%s)
                ORDER BY v.embedding <=> %s::vector ASC
                """,
                (literal, tenant, model_id, chunk_ids, literal),
            ).fetchall()
        scores = {str(row[0]): max(float(row[1]), 0.0) for row in rows}
        return normalize_scores(scores)

    @classmethod
    def connect(cls, dsn: str, *, dimension: int = DEFAULT_VECTOR_DIMENSION) -> PgVectorKnowledgeStore:
        pool = ConnectionPool(dsn, min_size=1, max_size=4, open=True)
        return cls(pool=pool, dimension=dimension)

    def close(self) -> None:
        self.pool.close()


def ensure_pgvector_extension(conn: Connection) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
