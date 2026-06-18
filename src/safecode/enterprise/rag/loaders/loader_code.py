"""Python code loader for enterprise RAG."""

from __future__ import annotations

import ast
from pathlib import Path

from safecode.enterprise.rag.exceptions import LoaderParseError, LoaderTooBigError
from safecode.enterprise.rag.ids import stable_record_id
from safecode.enterprise.rag.loaders._common import (
    LoaderEvent,
    LoaderResult,
    sanitize_loader_text,
    sort_records,
)
from safecode.enterprise.rag.source_registry import KnowledgeSource, RawRecord, Span

_MAX_FILE_BYTES = 2 * 1024 * 1024


def _iter_python_files(source: KnowledgeSource, project_root: Path) -> list[Path]:
    target = project_root / source.path_or_uri
    if target.is_file():
        return [target] if target.suffix == ".py" else []
    return sorted(path for path in target.rglob("*.py") if path.is_file())


def _load_python_file(
    source: KnowledgeSource,
    project_root: Path,
    file_path: Path,
    result: LoaderResult,
) -> None:
    rel_path = str(file_path.relative_to(project_root))
    size = file_path.stat().st_size
    if size > _MAX_FILE_BYTES:
        result.events.append(
            LoaderEvent(
                kind="warning",
                message="skipped file larger than 2 MB",
                path=rel_path,
            )
        )
        return

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=rel_path)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise LoaderParseError(f"failed to parse python file {rel_path}: {exc}") from exc

    lines = text.splitlines()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        block = "\n".join(lines[start_line - 1 : end_line])
        cleaned = sanitize_loader_text(block)
        result.records.append(
            RawRecord(
                record_id=stable_record_id(
                    source.source_id,
                    rel_path,
                    start_line,
                    end_line,
                    f"{type(node).__name__}:{node.name}",
                ),
                source_id=source.source_id,
                tenant_id=source.tenant_id,
                text=cleaned,
                path=rel_path,
                span=Span(start_line=start_line, end_line=end_line),
                metadata={
                    "symbol_kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "symbol_name": node.name,
                },
            )
        )


def load_code_source(source: KnowledgeSource, project_root: Path) -> LoaderResult:
    """Load top-level Python definitions into RawRecords."""
    result = LoaderResult()
    for file_path in _iter_python_files(source, project_root):
        _load_python_file(source, project_root, file_path, result)
    result.records = sort_records(result.records)
    return result
