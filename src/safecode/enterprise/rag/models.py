"""Enterprise RAG chunk and citation models.

中文模块说明：Chunk 与 Citation 的公共数据契约。
- 架构位置：RAG 全链路传递类型；workflow 节点与 trace 引用 citation_id。
- 安全不变量：citation 保留 source 身份；chunk 含 permission_scope 供过滤。
- 学习路径：读 ``ids.py`` 的 stable_citation_id 生成规则。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.rag.source_registry import SourceType

Freshness = Literal["current", "stale", "superseded", "unknown"]
PermissionVerdict = Literal["allowed", "restricted_to_subject", "denied"]


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source_id: str
    tenant_id: str = "local"
    path: str
    start_line: int
    end_line: int
    source_type: SourceType
    permission_scope: list[str]
    freshness: Freshness = "unknown"
    text: str
    hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    source_id: str
    source_type: SourceType
    tenant_id: str = "local"
    path: str
    start_line: int
    end_line: int
    score: float
    selection_reason: str
    permission_verdict: PermissionVerdict
    freshness: Freshness
    hash: str
    text_excerpt: str = ""
