"""Dispatch loader selection for a knowledge source."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.rag.exceptions import UnknownParserError
from safecode.enterprise.rag.loaders._common import LoaderResult
from safecode.enterprise.rag.loaders.loader_code import load_code_source
from safecode.enterprise.rag.loaders.loader_markdown import load_markdown_source
from safecode.enterprise.rag.loaders.loader_sarif import load_sarif_source
from safecode.enterprise.rag.loaders.loader_semgrep import load_semgrep_source
from safecode.enterprise.rag.source_registry import KnowledgeSource


def load_source(source: KnowledgeSource, project_root: Path) -> LoaderResult:
    if source.parser in {"markdown", "runbook"}:
        return load_markdown_source(source, project_root)
    if source.parser == "code":
        return load_code_source(source, project_root)
    if source.parser == "sarif":
        return load_sarif_source(source, project_root)
    if source.parser == "semgrep":
        return load_semgrep_source(source, project_root)
    raise UnknownParserError(f"unsupported parser: {source.parser}")
