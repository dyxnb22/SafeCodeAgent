"""Text chunker for embedding index (v6.3.0).

Splits files into bounded chunks suitable for embedding.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_CHUNK_LINES = 50        # lines per chunk
_CHUNK_MAX_CHARS = 2000  # hard cap per chunk
_MIN_CHUNK_CHARS = 20    # skip chunks that are too short to be meaningful

_SKIP_SUFFIXES = frozenset({
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".gz", ".tar", ".lock", ".db", ".sqlite",
    ".min.js", ".min.css",
})


@dataclass(frozen=True)
class TextChunk:
    """One chunk of text from a project file."""

    file_path: str
    chunk_index: int
    content: str
    content_hash: str   # sha256 of content


def chunk_file(file_path: str, project_root: Path) -> list[TextChunk]:
    """Read a file and return its chunks. Returns [] on any read error."""
    abs_path = project_root / file_path
    suffix = Path(file_path).suffix.lower()
    if suffix in _SKIP_SUFFIXES:
        return []
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    chunks: list[TextChunk] = []
    chunk_index = 0
    i = 0
    while i < len(lines):
        block = lines[i: i + _CHUNK_LINES]
        content = "\n".join(block)[:_CHUNK_MAX_CHARS]
        if len(content.strip()) >= _MIN_CHUNK_CHARS:
            chunks.append(
                TextChunk(
                    file_path=file_path,
                    chunk_index=chunk_index,
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest(),
                )
            )
            chunk_index += 1
        i += _CHUNK_LINES

    return chunks


def chunk_files(file_paths: list[str], project_root: Path) -> list[TextChunk]:
    """Chunk all given files. Silently skips files that fail to read."""
    result: list[TextChunk] = []
    for path in file_paths:
        result.extend(chunk_file(path, project_root))
    return result
