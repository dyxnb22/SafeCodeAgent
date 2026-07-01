"""Build in-memory chunk index from a knowledge manifest.

中文模块说明：从知识库 manifest 构建内存 chunk 索引，供检索器查询。
- 架构位置：RAG ingest 与离线 demo 的数据准备步骤。
- 安全不变量：chunk 携带 source_id、permission_scope；manifest 经 schema 校验。
- 学习路径：配合 ``source_registry.py`` 与 ``rag/pipeline.py``。
"""

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
