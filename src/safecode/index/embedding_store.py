"""SQLite-backed embedding store (v6.3.0).

Schema:
  chunks   — file chunks with content hashes and embedding blobs (JSON float arrays)
  index_meta — key-value store for model_id, last_built, etc.

The store is safe to read from multiple processes concurrently.
Writes are serialized via SQLite WAL mode.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safecode.index.chunker import TextChunk, chunk_files
from safecode.index.embedding_backend import EmbeddingBackend, NullEmbeddingBackend, cosine_similarity

_BATCH_SIZE = 32    # chunks per embedding batch
_SCHEMA_VERSION = "1"


@dataclass
class IndexStatus:
    exists: bool
    total_files: int
    total_chunks: int
    last_built: str | None
    model_id: str | None
    is_semantic: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "total_files": self.total_files,
            "total_chunks": self.total_chunks,
            "last_built": self.last_built,
            "model_id": self.model_id,
            "is_semantic": self.is_semantic,
        }


@dataclass(frozen=True)
class SemanticSearchResult:
    file_path: str
    chunk_index: int
    score: float
    snippet: str     # first 120 chars of the chunk


class EmbeddingStore:
    """Manages the SQLite embedding index at .sac/index/embeddings.db."""

    def __init__(self, sac_dir: Path, backend: EmbeddingBackend | None = None) -> None:
        self.db_path = sac_dir / "index" / "embeddings.db"
        self._backend = backend  # None = lazy-create on first write

    def _get_backend(self) -> EmbeddingBackend:
        if self._backend is None:
            from safecode.index.embedding_backend import create_embedding_backend
            self._backend = create_embedding_backend()
        return self._backend

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        file_paths: list[str],
        project_root: Path,
        *,
        force: bool = False,
    ) -> dict[str, int]:
        """Build or update the embedding index.

        Returns {"files_indexed": N, "chunks_added": M, "chunks_skipped": K}.
        """
        backend = self._get_backend()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        self._ensure_schema(con)

        all_chunks = chunk_files(file_paths, project_root)
        chunks_added = 0
        chunks_skipped = 0

        for i in range(0, len(all_chunks), _BATCH_SIZE):
            batch = all_chunks[i: i + _BATCH_SIZE]
            hashes = [c.content_hash for c in batch]

            if not force:
                existing = self._get_existing_hashes(con, hashes)
                to_embed = [c for c in batch if c.content_hash not in existing]
                chunks_skipped += len(batch) - len(to_embed)
            else:
                to_embed = batch

            if not to_embed:
                continue

            vectors = backend.embed([c.content for c in to_embed])
            con.executemany(
                """INSERT OR REPLACE INTO chunks
                   (file_path, chunk_index, content_hash, content, embedding, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        chunk.file_path,
                        chunk.chunk_index,
                        chunk.content_hash,
                        chunk.content[:500],
                        json.dumps(vec, separators=(",", ":")),
                        datetime.now(timezone.utc).isoformat(),
                    )
                    for chunk, vec in zip(to_embed, vectors)
                ],
            )
            chunks_added += len(to_embed)

        con.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            ("last_built", datetime.now(timezone.utc).isoformat()),
        )
        con.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            ("model_id", backend.model_id()),
        )
        con.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            ("schema_version", _SCHEMA_VERSION),
        )
        con.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            ("is_semantic", "1" if backend.is_semantic else "0"),
        )
        con.commit()
        con.close()

        files_indexed = len({c.file_path for c in all_chunks})
        return {
            "files_indexed": files_indexed,
            "chunks_added": chunks_added,
            "chunks_skipped": chunks_skipped,
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 10) -> list[SemanticSearchResult]:
        """Return files ranked by semantic similarity to query.

        Falls back to empty list if the index does not exist or backend is null.
        """
        if not self.db_path.exists():
            return []
        backend = self._get_backend()
        if not backend.is_semantic:
            return []

        query_vec = backend.embed([query])[0]
        con = self._connect(read_only=True)
        try:
            self._ensure_schema(con)
            rows = con.execute(
                "SELECT file_path, chunk_index, embedding, content FROM chunks"
            ).fetchall()
        finally:
            con.close()

        scored: list[tuple[float, str, int, str]] = []
        for file_path, chunk_index, emb_json, content in rows:
            try:
                vec = json.loads(emb_json)
                score = cosine_similarity(query_vec, vec)
            except Exception:
                continue
            scored.append((score, file_path, chunk_index, content or ""))

        scored.sort(key=lambda x: -x[0])
        # Deduplicate by file — keep highest score per file
        seen: dict[str, float] = {}
        results: list[SemanticSearchResult] = []
        for score, file_path, chunk_index, content in scored:
            if file_path not in seen:
                seen[file_path] = score
                results.append(SemanticSearchResult(
                    file_path=file_path,
                    chunk_index=chunk_index,
                    score=score,
                    snippet=content[:120],
                ))
            if len(results) >= limit:
                break

        return results

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> IndexStatus:
        if not self.db_path.exists():
            return IndexStatus(
                exists=False, total_files=0, total_chunks=0,
                last_built=None, model_id=None, is_semantic=False,
            )
        con = self._connect(read_only=True)
        try:
            self._ensure_schema(con)
            total_chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            total_files = con.execute(
                "SELECT COUNT(DISTINCT file_path) FROM chunks"
            ).fetchone()[0]
            meta = {
                row[0]: row[1]
                for row in con.execute("SELECT key, value FROM index_meta").fetchall()
            }
        finally:
            con.close()

        return IndexStatus(
            exists=True,
            total_files=total_files,
            total_chunks=total_chunks,
            last_built=meta.get("last_built"),
            model_id=meta.get("model_id"),
            is_semantic=meta.get("is_semantic") == "1",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = self.db_path.as_uri() + "?mode=ro"
            con = sqlite3.connect(uri, uri=True)
        else:
            con = sqlite3.connect(str(self.db_path))
            con.execute("PRAGMA journal_mode=WAL")
        return con

    def _ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                content TEXT,
                embedding TEXT,
                indexed_at TEXT NOT NULL,
                UNIQUE(file_path, chunk_index)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS index_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path)"
        )

    def _get_existing_hashes(
        self, con: sqlite3.Connection, hashes: list[str]
    ) -> set[str]:
        if not hashes:
            return set()
        placeholders = ",".join("?" * len(hashes))
        rows = con.execute(
            f"SELECT content_hash FROM chunks WHERE content_hash IN ({placeholders})",
            hashes,
        ).fetchall()
        return {row[0] for row in rows}
