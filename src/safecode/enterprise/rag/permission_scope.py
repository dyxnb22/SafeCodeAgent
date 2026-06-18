"""Permission scope assignment and filtering for enterprise RAG."""

from __future__ import annotations

from dataclasses import dataclass, field

from safecode.enterprise.rag.models import Chunk


@dataclass
class PermissionScopeResult:
    chunks: list[Chunk] = field(default_factory=list)
    events: list[dict[str, str]] = field(default_factory=list)


def assign_permission_scope(chunks: list[Chunk], permission_scope: list[str]) -> list[Chunk]:
    """Copy parent source permission_scope onto each chunk."""
    assigned: list[Chunk] = []
    for chunk in chunks:
        assigned.append(chunk.model_copy(update={"permission_scope": list(permission_scope)}))
    return assigned


def drop_unscoped_chunks(chunks: list[Chunk]) -> PermissionScopeResult:
    """Drop chunks without a permission scope and emit chunk.unscoped events."""
    result = PermissionScopeResult()
    for chunk in chunks:
        if not chunk.permission_scope:
            result.events.append(
                {
                    "type": "chunk.unscoped",
                    "chunk_id": chunk.chunk_id,
                    "source_id": chunk.source_id,
                }
            )
            continue
        result.chunks.append(chunk)
    return result


def actor_can_access_chunk(chunk: Chunk, actor_scope: list[str], actor_tenant: str = "local") -> bool:
    """Fail closed when tenant or permission scope does not match."""
    if chunk.tenant_id != actor_tenant:
        return False
    if not chunk.permission_scope:
        return False
    actor_tags = set(actor_scope)
    return set(chunk.permission_scope).issubset(actor_tags)
