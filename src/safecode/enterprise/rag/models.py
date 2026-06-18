"""Enterprise RAG chunk and citation models."""

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
