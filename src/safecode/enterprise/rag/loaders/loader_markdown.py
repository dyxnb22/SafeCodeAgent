"""Markdown and runbook loaders for enterprise RAG."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from safecode.enterprise.rag.ids import stable_record_id
from safecode.enterprise.rag.loaders._common import (
    LoaderResult,
    read_bounded_text,
    sanitize_loader_text,
    sort_records,
)
from safecode.enterprise.rag.source_registry import KnowledgeSource, RawRecord, Span

_FRONT_MATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _collect_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            level = len(match.group(1))
            headings.append(f"h{level}:{match.group(2).strip()}")
    return headings


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, text
    if not isinstance(parsed, dict):
        return {}, text[match.end() :]
    metadata = {str(key): str(value) for key, value in parsed.items()}
    return metadata, text[match.end() :]


def _h1_line_indices(lines: list[str]) -> list[int]:
    indices: list[int] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            indices.append(index)
    return indices


def _make_record(
    source: KnowledgeSource,
    path: str,
    lines: list[str],
    start_index: int,
    end_index: int,
    section_kind: str,
    extra_metadata: dict[str, str],
) -> RawRecord | None:
    block = "\n".join(lines[start_index : end_index + 1]).strip()
    if not block:
        return None
    text = sanitize_loader_text(block)
    start_line = start_index + 1
    end_line = end_index + 1
    metadata = dict(extra_metadata)
    metadata["headings"] = _collect_headings(text)
    return RawRecord(
        record_id=stable_record_id(source.source_id, path, start_line, end_line, section_kind),
        source_id=source.source_id,
        tenant_id=source.tenant_id,
        text=text,
        path=path,
        span=Span(start_line=start_line, end_line=end_line),
        metadata=metadata,
    )


def load_markdown_source(source: KnowledgeSource, project_root: Path) -> LoaderResult:
    """Load Markdown into H1-scoped RawRecords."""
    target = project_root / source.path_or_uri
    paths = [target] if target.is_file() else sorted(target.rglob("*.md"))
    result = LoaderResult()

    for file_path in paths:
        rel_path = str(file_path.relative_to(project_root))
        text = read_bounded_text(file_path)
        front_matter, body = _split_front_matter(text)
        lines = body.splitlines()
        h1_indices = _h1_line_indices(lines)

        if not h1_indices:
            record = _make_record(
                source,
                rel_path,
                lines,
                0,
                max(len(lines) - 1, 0),
                "whole",
                front_matter,
            )
            if record is not None:
                result.records.append(record)
            continue

        if h1_indices[0] > 0 and any(line.strip() for line in lines[: h1_indices[0]]):
            preamble = _make_record(
                source,
                rel_path,
                lines,
                0,
                h1_indices[0] - 1,
                "preamble",
                front_matter,
            )
            if preamble is not None:
                result.records.append(preamble)

        for index, start in enumerate(h1_indices):
            end = (h1_indices[index + 1] - 1) if index + 1 < len(h1_indices) else len(lines) - 1
            record = _make_record(
                source,
                rel_path,
                lines,
                start,
                end,
                f"h1-{index}",
                front_matter,
            )
            if record is not None:
                result.records.append(record)

    result.records = sort_records(result.records)
    return result
