"""Deterministic identifiers for enterprise RAG records and chunks."""

from __future__ import annotations

import hashlib


def stable_hash(*parts: str) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_record_id(
    source_id: str,
    path: str,
    start_line: int,
    end_line: int,
    section_kind: str,
) -> str:
    digest = stable_hash(source_id, path, str(start_line), str(end_line), section_kind)
    return f"record-{digest[:24]}"


def stable_chunk_id(
    source_id: str,
    path: str,
    start_line: int,
    end_line: int,
    text_hash: str,
) -> str:
    digest = stable_hash(source_id, path, str(start_line), str(end_line), text_hash)
    return f"chunk-{digest[:24]}"


def stable_citation_id(
    source_id: str,
    path: str,
    start_line: int,
    end_line: int,
    text_hash: str,
) -> str:
    digest = stable_hash("cite", source_id, path, str(start_line), str(end_line), text_hash)
    return f"cite-{digest[:24]}"


def text_sha256(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
