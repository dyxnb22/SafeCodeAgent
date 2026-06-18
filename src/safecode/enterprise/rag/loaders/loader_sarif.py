"""SARIF loader for enterprise RAG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safecode.enterprise.rag.exceptions import LoaderParseError, UnsupportedSarifVersionError
from safecode.enterprise.rag.ids import stable_record_id
from safecode.enterprise.rag.loaders._common import (
    LoaderResult,
    read_bounded_text,
    sanitize_loader_text,
    sort_records,
)
from safecode.enterprise.rag.source_registry import KnowledgeSource, RawRecord, Span

_SUPPORTED_SARIF_VERSION = "2.1.0"


def _extract_results(document: dict[str, Any]) -> list[dict[str, Any]]:
    runs = document.get("runs")
    if not isinstance(runs, list):
        return []
    results: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_results = run.get("results")
        if isinstance(run_results, list):
            results.extend(item for item in run_results if isinstance(item, dict))
    return results


def _result_location(result: dict[str, Any]) -> tuple[str, int, int]:
    locations = result.get("locations")
    if not isinstance(locations, list) or not locations:
        return "unknown", 1, 1
    first = locations[0]
    if not isinstance(first, dict):
        return "unknown", 1, 1
    physical = first.get("physicalLocation")
    if not isinstance(physical, dict):
        return "unknown", 1, 1
    artifact = physical.get("artifactLocation")
    path = "unknown"
    if isinstance(artifact, dict) and isinstance(artifact.get("uri"), str):
        path = artifact["uri"]
    region = physical.get("region")
    start_line = 1
    end_line = 1
    if isinstance(region, dict):
        if isinstance(region.get("startLine"), int):
            start_line = region["startLine"]
        if isinstance(region.get("endLine"), int):
            end_line = region["endLine"]
        elif isinstance(region.get("startLine"), int):
            end_line = region["startLine"]
    return path, start_line, end_line


def load_sarif_source(source: KnowledgeSource, project_root: Path) -> LoaderResult:
    """Parse SARIF 2.1.0 findings into RawRecords."""
    file_path = project_root / source.path_or_uri
    raw_text = read_bounded_text(file_path)
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LoaderParseError(f"invalid SARIF JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise LoaderParseError("SARIF root must be an object")

    version = document.get("version")
    if version != _SUPPORTED_SARIF_VERSION:
        raise UnsupportedSarifVersionError(
            f"unsupported SARIF version {version!r}; expected {_SUPPORTED_SARIF_VERSION!r}"
        )

    result = LoaderResult()
    for index, item in enumerate(_extract_results(document)):
        path, start_line, end_line = _result_location(item)
        message = ""
        msg_obj = item.get("message")
        if isinstance(msg_obj, dict) and isinstance(msg_obj.get("text"), str):
            message = msg_obj["text"]
        rule_id = item.get("ruleId")
        if not isinstance(rule_id, str):
            rule_id = f"result-{index}"
        text = sanitize_loader_text(message or rule_id)
        result.records.append(
            RawRecord(
                record_id=stable_record_id(
                    source.source_id,
                    path,
                    start_line,
                    end_line,
                    f"sarif:{rule_id}:{index}",
                ),
                source_id=source.source_id,
                tenant_id=source.tenant_id,
                text=text,
                path=path,
                span=Span(start_line=start_line, end_line=end_line),
                metadata={
                    "rule_id": rule_id,
                    "level": str(item.get("level", "unknown")),
                },
            )
        )

    result.records = sort_records(result.records)
    return result
