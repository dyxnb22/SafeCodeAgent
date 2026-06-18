"""Shared loader helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from safecode.context.redactor import redact_secrets
from safecode.enterprise.rag.exceptions import LoaderTooBigError
from safecode.enterprise.rag.source_registry import RawRecord

_MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class LoaderEvent:
    kind: Literal["warning", "info"]
    message: str
    path: str


@dataclass
class LoaderResult:
    records: list[RawRecord] = field(default_factory=list)
    events: list[LoaderEvent] = field(default_factory=list)


def read_bounded_text(path: Path) -> str:
    size = path.stat().st_size
    if size > _MAX_FILE_BYTES:
        raise LoaderTooBigError(f"file exceeds 2 MB limit: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def sanitize_loader_text(text: str) -> str:
    return redact_secrets(text)


def sort_records(records: list[RawRecord]) -> list[RawRecord]:
    return sorted(records, key=lambda record: (record.path, record.span.start_line, record.record_id))
