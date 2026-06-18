"""Build in-memory chunk index from a knowledge manifest."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.rag.chunker import chunk_records
from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.permission_scope import assign_permission_scope, drop_unscoped_chunks
from safecode.enterprise.rag.pipeline import load_source
from safecode.enterprise.rag.source_registry import SourceRegistry


def build_chunks_from_manifest(manifest_path: Path | str, project_root: Path | str) -> list[Chunk]:
    root = Path(project_root)
    registry = SourceRegistry.from_manifest(manifest_path)
    chunks: list[Chunk] = []
    for source in registry.list_sources():
        records = load_source(source, root).records
        produced = chunk_records(records, source)
        scoped = assign_permission_scope(produced, source.permission_scope)
        kept = drop_unscoped_chunks(scoped).chunks
        chunks.extend(kept)
    return sorted(chunks, key=lambda chunk: (chunk.source_id, chunk.path, chunk.start_line, chunk.chunk_id))
