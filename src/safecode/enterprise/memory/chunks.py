"""Convert admitted memory facts into permission-scoped retrieval chunks."""

from __future__ import annotations

from safecode.context.redactor import redact_secrets
from safecode.enterprise.memory.models import MemoryFact
from safecode.enterprise.memory.store import MemoryFactStore
from safecode.enterprise.rag.ids import stable_chunk_id, text_sha256
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.source_registry import SourceType


def memory_fact_to_chunk(fact: MemoryFact) -> Chunk:
    text = redact_secrets(fact.content)
    content_hash = text_sha256(text)
    path = f"memory://{fact.fact_id}"
    return Chunk(
        chunk_id=stable_chunk_id("memory", path, 1, 1, content_hash),
        source_id=f"memory:{fact.fact_id}",
        tenant_id=fact.tenant_id,
        path=path,
        start_line=1,
        end_line=1,
        source_type=SourceType.historical_fix,
        permission_scope=list(fact.permission_scope),
        freshness="current",
        text=text,
        hash=content_hash,
        metadata={
            "fact_id": fact.fact_id,
            "provenance": fact.provenance,
            "approver": fact.approver,
        },
    )


def active_memory_chunks(store: MemoryFactStore, tenant_id: str) -> list[Chunk]:
    return [memory_fact_to_chunk(fact) for fact in store.list_active(tenant_id)]
