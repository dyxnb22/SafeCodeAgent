"""Enterprise knowledge source registry models and manifest loader.

中文模块说明：知识源注册表与 manifest 加载，声明哪些文档可进入 RAG。
- 架构位置：RAG Data 平面元数据；ingest 与检索的前置条件。
- 安全不变量：source 带 tenant 与 permission；未注册源不会被检索。
- 学习路径：读 ``tests/enterprise/rag/test_source_registry.py``。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from safecode.enterprise.rag.exceptions import (
    DuplicateSourceIdError,
    ManifestValidationError,
    UnknownParserError,
    UnknownSourceTypeError,
)

_REQUIRED_MANIFEST_KEYS = (
    "source_id",
    "source_type",
    "name",
    "path_or_uri",
    "owner",
    "permission_scope",
    "refresh_cadence",
    "parser",
)


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


class SourceRegistry(BaseModel):
    """In-memory registry of configured knowledge sources."""

    model_config = ConfigDict(extra="forbid")

    sources: dict[str, KnowledgeSource] = Field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest_path: Path | str) -> SourceRegistry:
        """Load and validate a YAML manifest without reading source content."""
        path = Path(manifest_path)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ManifestValidationError(f"manifest: invalid YAML: {exc}") from exc

        if not isinstance(raw, dict):
            raise ManifestValidationError("manifest: root must be a mapping")

        entries = raw.get("sources")
        if not isinstance(entries, list):
            raise ManifestValidationError("sources: must be a list")

        registry = cls()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ManifestValidationError(f"sources[{index}]: must be a mapping")

            for key in _REQUIRED_MANIFEST_KEYS:
                if key not in entry:
                    raise ManifestValidationError(f"sources[{index}]: missing required key '{key}'")

            source_id = entry["source_id"]
            if not isinstance(source_id, str) or not source_id.strip():
                raise ManifestValidationError(f"sources[{index}]: source_id must be a non-empty string")

            if source_id in registry.sources:
                raise DuplicateSourceIdError(f"duplicate source_id: {source_id}")

            source_type_raw = entry["source_type"]
            if not isinstance(source_type_raw, str):
                raise ManifestValidationError(f"sources[{index}]: source_type must be a string")
            try:
                source_type = SourceType(source_type_raw)
            except ValueError as exc:
                raise UnknownSourceTypeError(
                    f"sources[{index}]: unknown source_type '{source_type_raw}'"
                ) from exc

            parser_raw = entry["parser"]
            if not isinstance(parser_raw, str):
                raise ManifestValidationError(f"sources[{index}]: parser must be a string")
            if parser_raw not in {"markdown", "code", "sarif", "semgrep", "runbook"}:
                raise UnknownParserError(f"sources[{index}]: unknown parser '{parser_raw}'")

            permission_scope = entry["permission_scope"]
            if not isinstance(permission_scope, list) or not all(
                isinstance(item, str) for item in permission_scope
            ):
                raise ManifestValidationError(
                    f"sources[{index}]: permission_scope must be a list of strings"
                )

            metadata = entry.get("metadata", {})
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()
            ):
                raise ManifestValidationError(f"sources[{index}]: metadata must be a string map")

            tenant_id = entry.get("tenant_id", "local")
            if not isinstance(tenant_id, str) or not tenant_id.strip():
                raise ManifestValidationError(f"sources[{index}]: tenant_id must be a non-empty string")

            try:
                source = KnowledgeSource(
                    source_id=source_id,
                    source_type=source_type,
                    tenant_id=tenant_id,
                    name=str(entry["name"]),
                    path_or_uri=str(entry["path_or_uri"]),
                    owner=str(entry["owner"]),
                    permission_scope=list(permission_scope),
                    refresh_cadence=entry["refresh_cadence"],
                    parser=parser_raw,
                    metadata=dict(metadata),
                )
            except ValidationError as exc:
                raise ManifestValidationError(
                    f"sources[{index}]: invalid field values: {exc.errors()[0]['loc']}"
                ) from exc

            registry.sources[source_id] = source

        return registry

    def get(self, source_id: str) -> KnowledgeSource:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ManifestValidationError(f"unknown source_id: {source_id}") from exc

    def list_sources(self) -> list[KnowledgeSource]:
        return [self.sources[key] for key in sorted(self.sources)]
