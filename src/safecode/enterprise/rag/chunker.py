"""Enterprise chunker adapter over RawRecords."""

from __future__ import annotations

import re
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.rag.ids import stable_chunk_id, text_sha256
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.source_registry import KnowledgeSource, RawRecord, SourceType

_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_MAX_CHUNK_CHARS = 8192


def _freshness_for_source(source: KnowledgeSource) -> str:
    if source.refresh_cadence == "static":
        return "current"
    if source.refresh_cadence == "daily":
        return "unknown"
    return "unknown"


def _split_markdown_text(text: str) -> list[tuple[str, dict[str, str]]]:
    matches = list(_H2_RE.finditer(text))
    if not matches:
        return [(text, {})]
    parts: list[tuple[str, dict[str, str]]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[start:end].strip()
        if section:
            parts.append((section, {"headings": [f"h2:{match.group(1).strip()}"]}))
    return parts or [(text, {})]


def _split_oversized(text: str) -> list[str]:
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        return [text[:_MAX_CHUNK_CHARS]]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= _MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph[:_MAX_CHUNK_CHARS]
    if current:
        chunks.append(current)
    return chunks or [text[:_MAX_CHUNK_CHARS]]


def _record_to_chunks(record: RawRecord, source: KnowledgeSource) -> list[Chunk]:
    if source.source_type in {
        SourceType.security_policy,
        SourceType.secure_coding_standard,
        SourceType.runbook,
        SourceType.architecture_doc,
        SourceType.project_doc,
    }:
        sections = _split_markdown_text(record.text)
    else:
        sections = [(record.text, {})]

    chunks: list[Chunk] = []
    for section_text, section_meta in sections:
        for piece in _split_oversized(section_text):
            cleaned = redact_secrets(piece)
            text_hash = text_sha256(cleaned)
            metadata = dict(record.metadata)
            metadata.update(section_meta)
            chunks.append(
                Chunk(
                    chunk_id=stable_chunk_id(
                        source.source_id,
                        record.path,
                        record.span.start_line,
                        record.span.end_line,
                        text_hash,
                    ),
                    source_id=source.source_id,
                    tenant_id=source.tenant_id,
                    path=record.path,
                    start_line=record.span.start_line,
                    end_line=record.span.end_line,
                    source_type=source.source_type,
                    permission_scope=list(source.permission_scope),
                    freshness=_freshness_for_source(source),
                    text=cleaned,
                    hash=text_hash,
                    metadata=metadata,
                )
            )
    return chunks


def chunk_records(records: list[RawRecord], source: KnowledgeSource) -> list[Chunk]:
    """Convert loader records into enterprise Chunk objects."""
    chunks: list[Chunk] = []
    for record in records:
        chunks.extend(_record_to_chunks(record, source))
    return sorted(chunks, key=lambda chunk: (chunk.path, chunk.start_line, chunk.chunk_id))


def chunk_source_records(
    source: KnowledgeSource,
    records: list[RawRecord],
    project_root: Path | None = None,
) -> list[Chunk]:
    """Chunk records for a source; project_root reserved for legacy adapter hooks."""
    _ = project_root
    return chunk_records(records, source)
