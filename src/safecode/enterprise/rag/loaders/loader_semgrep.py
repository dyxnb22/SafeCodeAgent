"""Semgrep JSON loader for enterprise RAG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safecode.enterprise.rag.exceptions import LoaderParseError
from safecode.enterprise.rag.ids import stable_record_id
from safecode.enterprise.rag.loaders._common import (
    LoaderResult,
    read_bounded_text,
    sanitize_loader_text,
    sort_records,
)
from safecode.enterprise.rag.source_registry import KnowledgeSource, RawRecord, Span


def _result_lines(item: dict[str, Any]) -> tuple[int, int]:
    start = item.get("start")
    end = item.get("end")
    start_line = 1
    end_line = 1
    if isinstance(start, dict) and isinstance(start.get("line"), int):
        start_line = start["line"]
    if isinstance(end, dict) and isinstance(end.get("line"), int):
        end_line = end["line"]
    else:
        end_line = start_line
    return start_line, end_line


def load_semgrep_source(source: KnowledgeSource, project_root: Path) -> LoaderResult:
    """Parse Semgrep JSON results into RawRecords."""
    file_path = project_root / source.path_or_uri
    raw_text = read_bounded_text(file_path)
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LoaderParseError(f"invalid Semgrep JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise LoaderParseError("Semgrep root must be an object")

    findings = document.get("results")
    if not isinstance(findings, list):
        raise LoaderParseError("Semgrep document missing results array")

    result = LoaderResult()
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "unknown"))
        start_line, end_line = _result_lines(item)
        check_id = str(item.get("check_id", f"finding-{index}"))
        extra = item.get("extra")
        message = check_id
        if isinstance(extra, dict) and isinstance(extra.get("message"), str):
            message = extra["message"]
        text = sanitize_loader_text(message)
        result.records.append(
            RawRecord(
                record_id=stable_record_id(
                    source.source_id,
                    path,
                    start_line,
                    end_line,
                    f"semgrep:{check_id}:{index}",
                ),
                source_id=source.source_id,
                tenant_id=source.tenant_id,
                text=text,
                path=path,
                span=Span(start_line=start_line, end_line=end_line),
                metadata={
                    "check_id": check_id,
                    "severity": str(extra.get("severity", "unknown")) if isinstance(extra, dict) else "unknown",
                },
            )
        )

    result.records = sort_records(result.records)
    return result
