"""Hybrid enterprise retriever with permission-aware filtering."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from safecode.context.redactor import redact_secrets
from safecode.enterprise.rag.ids import stable_citation_id
from safecode.enterprise.rag.lexical import score_chunks as lexical_scores
from safecode.enterprise.rag.models import Chunk, Citation
from safecode.enterprise.rag.permission_scope import actor_can_access_chunk
from safecode.enterprise.rag.semantic import DeterministicEmbeddingBackend, score_chunks as semantic_scores
from safecode.enterprise.rag.source_registry import SourceType
from safecode.index.embedding_backend import EmbeddingBackend

_MAX_EXCERPT_CHARS = 1024
_DEFAULT_LEXICAL_WEIGHT = 0.5
_DEFAULT_SEMANTIC_WEIGHT = 0.5


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_types: list[SourceType] | None = None
    path_prefixes: list[str] | None = None
    cwe_tags: list[str] | None = None
    pinned_paths: list[str] | None = None


@dataclass
class HybridRetriever:
    chunks: list[Chunk]
    lexical_weight: float = _DEFAULT_LEXICAL_WEIGHT
    semantic_weight: float = _DEFAULT_SEMANTIC_WEIGHT
    embedding_backend: EmbeddingBackend = field(default_factory=DeterministicEmbeddingBackend)
    denied_events: list[dict[str, str]] = field(default_factory=list)

    def retrieve(
        self,
        query: str,
        k: int,
        actor_scope: list[str],
        *,
        actor_tenant: str = "local",
        filters: RetrievalFilters | None = None,
    ) -> list[Citation]:
        allowed = self._filter_candidates(actor_scope, actor_tenant, filters)
        if not allowed:
            return []

        lex = lexical_scores(query, allowed)
        sem = semantic_scores(query, allowed, backend=self.embedding_backend)
        ranked: list[tuple[float, Chunk, str]] = []
        for chunk in allowed:
            combined = (self.lexical_weight * lex.get(chunk.chunk_id, 0.0)) + (
                self.semantic_weight * sem.get(chunk.chunk_id, 0.0)
            )
            reason = (
                f"lex={lex.get(chunk.chunk_id, 0.0):.2f},"
                f"sem={sem.get(chunk.chunk_id, 0.0):.2f}"
            )
            ranked.append((combined, chunk, reason))

        ranked.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line, item[1].chunk_id))
        citations: list[Citation] = []
        for score, chunk, reason in ranked[:k]:
            excerpt = redact_secrets(chunk.text)[:_MAX_EXCERPT_CHARS]
            if len(chunk.text) > _MAX_EXCERPT_CHARS:
                excerpt += "…"
            citations.append(
                Citation(
                    citation_id=stable_citation_id(
                        chunk.source_id,
                        chunk.path,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.hash,
                    ),
                    source_id=chunk.source_id,
                    source_type=chunk.source_type,
                    tenant_id=chunk.tenant_id,
                    path=chunk.path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    score=score,
                    selection_reason=reason,
                    permission_verdict="allowed",
                    freshness=chunk.freshness,
                    hash=chunk.hash,
                    text_excerpt=excerpt,
                )
            )
        return citations

    def _filter_candidates(
        self,
        actor_scope: list[str],
        actor_tenant: str,
        filters: RetrievalFilters | None,
    ) -> list[Chunk]:
        allowed: list[Chunk] = []
        for chunk in self.chunks:
            if not actor_can_access_chunk(chunk, actor_scope, actor_tenant=actor_tenant):
                self.denied_events.append(
                    {
                        "type": "retrieval.permission_denied",
                        "chunk_id": chunk.chunk_id,
                    }
                )
                continue
            if filters and filters.source_types and chunk.source_type not in filters.source_types:
                continue
            if filters and filters.path_prefixes and not any(
                chunk.path.startswith(prefix) for prefix in filters.path_prefixes
            ):
                continue
            if filters and filters.cwe_tags:
                cwe = str(chunk.metadata.get("cwe", ""))
                if cwe and cwe not in filters.cwe_tags:
                    continue
            allowed.append(chunk)
        return allowed
