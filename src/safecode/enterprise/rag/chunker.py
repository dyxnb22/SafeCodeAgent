"""Enterprise chunker adapter over RawRecords.

将 loader 产出的 RawRecord 切分为带权限边界的 Chunk。
每个 Chunk 继承 source.permission_scope 与 tenant_id，供检索阶段按主体过滤。
分块前对文本做秘密脱敏；chunk_id 由来源、路径、行号与内容哈希稳定生成。
"""

from __future__ import annotations

import re
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.rag.ids import stable_chunk_id, text_sha256
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.source_registry import KnowledgeSource, RawRecord, SourceType

_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_MAX_CHUNK_CHARS = 8192  # 单块字符上限，防止超大块绕过上下文预算或拖慢检索


def _freshness_for_source(source: KnowledgeSource) -> str:
    """根据刷新节奏标注新鲜度；非 static 源目前均标为 unknown。

    潜在问题：daily 与其它动态源未区分，可能影响新鲜度感知与排序。
    """
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
    """将单条 RawRecord 转为一个或多个 Chunk，携带 permission_scope 与脱敏文本。

    文档类 source_type 按 ## 标题切分；其它类型整段切分后再按 _MAX_CHUNK_CHARS 拆分。
    permission_scope 从 source 继承——检索时必须与主体权限范围求交，不可默认全量可见。
    """
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
    """将 loader 记录批量转为企业 Chunk 对象，按路径与行号排序。"""
    chunks: list[Chunk] = []
    for record in records:
        chunks.extend(_record_to_chunks(record, source))
    return sorted(chunks, key=lambda chunk: (chunk.path, chunk.start_line, chunk.chunk_id))


def chunk_source_records(
    source: KnowledgeSource,
    records: list[RawRecord],
    project_root: Path | None = None,
) -> list[Chunk]:
    """为指定 source 分块；project_root 保留给遗留适配钩子，当前未使用。"""
    _ = project_root
    return chunk_records(records, source)
