"""Permission scope assignment and filtering for enterprise RAG.

中文模块说明：把 RBAC 角色映射为检索作用域（org/appsec/repo 等），并过滤 chunk。
- 架构位置：``retriever.py`` 在打分后调用 ``actor_can_access_chunk``。
- 安全不变量：显式 scope 不随角色自动扩张；viewer 通常仅 org 级；缺权限即不可见。
- 学习路径：对照 ``rbac/models.py`` 与 ``workflow/test_retrieval_actor_scope.py``。
"""

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
