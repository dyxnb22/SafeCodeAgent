"""Hybrid enterprise retriever with permission-aware filtering.

中文模块说明：企业 RAG 检索入口，混合 lexical + semantic 打分并按权限过滤。
- 架构位置：Workflow 的 retrieve 节点调用；输入 actor scope，输出带 citation_id 的 Chunk 列表。
- 安全不变量：检索结果是证据而非执行指令；越权 chunk 被丢弃；内容送模型前经 ``redact_secrets``。
- 与内核关系：lexical/semantic 可复用 kernel context 原语；权限判定在 Enterprise ``permission_scope``。
- 学习路径：配合 ``index_builder.py``、``source_registry.py`` 与 ``test_retrieval_actor_scope.py``。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from safecode.context.redactor import redact_secrets
from safecode.enterprise.rag.ids import stable_citation_id
from safecode.enterprise.rag.lexical import score_chunks as lexical_scores
from safecode.enterprise.rag.models import Chunk, Citation
from safecode.enterprise.rag.permission_scope import actor_can_access_chunk
from safecode.enterprise.rag.query_rewrite import rewrite_query
from safecode.enterprise.rag.reranker import RerankCandidate, query_terms, rerank_candidates
from safecode.enterprise.rag.semantic import DeterministicEmbeddingBackend, score_chunks as semantic_scores
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.rag.vector_store import KnowledgeVectorStore
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
    vector_store: KnowledgeVectorStore | None = None
    actor_tenant: str = "local"
    use_reranker: bool = False
    denied_events: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_vector_store(
        cls,
        store: KnowledgeVectorStore,
        tenant_id: str,
        *,
        lexical_weight: float = _DEFAULT_LEXICAL_WEIGHT,
        semantic_weight: float = _DEFAULT_SEMANTIC_WEIGHT,
        embedding_backend: EmbeddingBackend | None = None,
    ) -> HybridRetriever:
        return cls(
            chunks=store.list_chunks(tenant_id),
            lexical_weight=lexical_weight,
            semantic_weight=semantic_weight,
            embedding_backend=embedding_backend or DeterministicEmbeddingBackend(),
            vector_store=store,
            actor_tenant=tenant_id,
        )

    def retrieve(
        self,
        query: str,
        k: int,
        actor_scope: list[str],
        *,
        actor_tenant: str | None = None,
        filters: RetrievalFilters | None = None,
    ) -> list[Citation]:
        effective_tenant = actor_tenant if actor_tenant is not None else self.actor_tenant
        if self.vector_store is not None:
            self.chunks = self.vector_store.list_chunks(effective_tenant)
        rewritten = rewrite_query(query)
        allowed = self._filter_candidates(actor_scope, effective_tenant, filters)
        if not allowed:
            return []

        lex = lexical_scores(rewritten, allowed)
        if self.vector_store is not None:
            sem = self.vector_store.semantic_scores(
                self.actor_tenant,
                rewritten,
                [chunk.chunk_id for chunk in allowed],
                backend=self.embedding_backend,
            )
        else:
            sem = semantic_scores(rewritten, allowed, backend=self.embedding_backend)
        ranked: list[tuple[float, Chunk, str, float, float]] = []
        for chunk in allowed:
            combined = (self.lexical_weight * lex.get(chunk.chunk_id, 0.0)) + (
                self.semantic_weight * sem.get(chunk.chunk_id, 0.0)
            )
            lex_score = lex.get(chunk.chunk_id, 0.0)
            sem_score = sem.get(chunk.chunk_id, 0.0)
            reason = f"lex={lex_score:.2f},sem={sem_score:.2f}"
            ranked.append((combined, chunk, reason, lex_score, sem_score))

        if self.use_reranker:
            candidates = [
                RerankCandidate(
                    chunk=chunk,
                    base_score=score,
                    lexical_score=lex_score,
                    semantic_score=sem_score,
                )
                for score, chunk, _, lex_score, sem_score in ranked
            ]
            reranked = rerank_candidates(candidates, query_terms=query_terms(rewritten))
            ranked = [
                (
                    (self.lexical_weight * item.lexical_score)
                    + (self.semantic_weight * item.semantic_score),
                    item.chunk,
                    f"lex={item.lexical_score:.2f},sem={item.semantic_score:.2f},rerank=1",
                    item.lexical_score,
                    item.semantic_score,
                )
                for item in reranked
            ]
        else:
            ranked.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line, item[1].chunk_id))

        citations: list[Citation] = []
        for score, chunk, reason, _, _ in ranked[:k]:
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
