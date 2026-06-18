"""Enterprise knowledge source registry models and manifest loader."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    security_policy = "security_policy"
    secure_coding_standard = "secure_coding_standard"
    architecture_doc = "architecture_doc"
    project_doc = "project_doc"
    code = "code"
    historical_fix = "historical_fix"
    scanner_finding = "scanner_finding"
    runbook = "runbook"


ParserName = Literal["markdown", "code", "sarif", "semgrep", "runbook"]
RefreshCadence = Literal["static", "daily", "on_demand"]


class KnowledgeSource(BaseModel):
    """Describes one retrievable knowledge source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: SourceType
    tenant_id: str = "local"
    name: str
    path_or_uri: str
    owner: str
    permission_scope: list[str]
    refresh_cadence: RefreshCadence
    parser: ParserName
    metadata: dict[str, str] = Field(default_factory=dict)


class Span(BaseModel):
    """Line span within a source file (1-indexed, inclusive)."""

    model_config = ConfigDict(extra="forbid")

    start_line: int
    end_line: int


class RawRecord(BaseModel):
    """In-memory loader output prior to chunking."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    source_id: str
    tenant_id: str = "local"
    text: str
    path: str
    span: Span
    metadata: dict[str, Any] = Field(default_factory=dict)
