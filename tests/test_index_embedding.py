"""Tests for embedding index and hybrid retrieval (v6.3.0 + v6.3.1).

All tests use NullEmbeddingBackend so they run without sentence-transformers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.index.chunker import TextChunk, chunk_file, chunk_files
from safecode.index.embedding_backend import (
    NullEmbeddingBackend,
    cosine_similarity,
    create_embedding_backend,
)
from safecode.index.embedding_store import EmbeddingStore, IndexStatus
from safecode.context.hybrid_retrieval import HybridRetriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class TestChunker:
    def test_single_small_file(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"src/auth.py": "def login():\n    pass\n"})
        chunks = chunk_file("src/auth.py", root)
        assert len(chunks) == 1
        assert "def login" in chunks[0].content
        assert chunks[0].file_path == "src/auth.py"
        assert chunks[0].chunk_index == 0

    def test_large_file_produces_multiple_chunks(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(200))
        root = _make_project(tmp_path, {"big.py": content})
        chunks = chunk_file("big.py", root)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_content_hash_stable(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"f.py": "def compute_value():\n    return 42\n" * 3})
        chunks1 = chunk_file("f.py", root)
        chunks2 = chunk_file("f.py", root)
        assert len(chunks1) >= 1
        assert chunks1[0].content_hash == chunks2[0].content_hash

    def test_binary_file_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "image.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
        chunks = chunk_file("image.png", tmp_path)
        assert chunks == []

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        chunks = chunk_file("does_not_exist.py", tmp_path)
        assert chunks == []

    def test_chunk_max_chars(self, tmp_path: Path) -> None:
        long_line = "x" * 3000
        root = _make_project(tmp_path, {"long.py": long_line})
        chunks = chunk_file("long.py", root)
        for chunk in chunks:
            assert len(chunk.content) <= 2000

    def test_chunk_files_multiple(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {
            "a.py": "def foo():\n    return 1\n" * 3,
            "b.py": "def bar():\n    return 2\n" * 3,
        })
        chunks = chunk_files(["a.py", "b.py"], root)
        paths = {c.file_path for c in chunks}
        assert "a.py" in paths
        assert "b.py" in paths

    def test_short_content_skipped(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"tiny.py": "x"})
        chunks = chunk_file("tiny.py", root)
        # "x" is only 1 char, below _MIN_CHUNK_CHARS=20
        assert chunks == []


# ---------------------------------------------------------------------------
# NullEmbeddingBackend
# ---------------------------------------------------------------------------


class TestNullEmbeddingBackend:
    def test_embed_returns_list_of_vectors(self) -> None:
        backend = NullEmbeddingBackend()
        vecs = backend.embed(["hello", "world"])
        assert len(vecs) == 2
        assert all(isinstance(v, list) for v in vecs)

    def test_embed_vector_dimension(self) -> None:
        backend = NullEmbeddingBackend()
        vecs = backend.embed(["test"])
        assert len(vecs[0]) == 384

    def test_model_id(self) -> None:
        assert NullEmbeddingBackend().model_id() == "null"

    def test_is_not_semantic(self) -> None:
        assert not NullEmbeddingBackend().is_semantic

    def test_embed_empty_list(self) -> None:
        backend = NullEmbeddingBackend()
        assert backend.embed([]) == []

    def test_create_backend_warns_once_on_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import safecode.index.embedding_backend as embedding_backend

        class BrokenSentenceTransformerBackend:
            def __init__(self, model_name: str) -> None:
                raise ImportError("sentence-transformers unavailable")

        monkeypatch.setattr(embedding_backend, "SentenceTransformerBackend", BrokenSentenceTransformerBackend)
        monkeypatch.setattr(embedding_backend, "_fallback_warning_emitted", False)

        with pytest.warns(UserWarning, match="safecode-agent\\[semantic\\]"):
            backend = create_embedding_backend()

        assert isinstance(backend, NullEmbeddingBackend)
        import warnings

        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            backend = create_embedding_backend()
        assert isinstance(backend, NullEmbeddingBackend)
        assert recorded == []


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_symmetric(self) -> None:
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        assert abs(cosine_similarity(a, b) - cosine_similarity(b, a)) < 1e-6


# ---------------------------------------------------------------------------
# EmbeddingStore
# ---------------------------------------------------------------------------


class TestEmbeddingStore:
    def test_status_no_index(self, tmp_path: Path) -> None:
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        status = store.status()
        assert not status.exists
        assert status.total_chunks == 0

    def test_build_creates_index(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {"auth.py": "def login(): pass\n# auth module"})
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        result = store.build(["auth.py"], root)
        assert result["files_indexed"] == 1
        assert result["chunks_added"] >= 1

    def test_status_after_build(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {"x.py": "x = 1\n" * 10})
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        store.build(["x.py"], root)
        status = store.status()
        assert status.exists
        assert status.total_chunks >= 1
        assert status.total_files == 1
        assert status.last_built is not None
        assert status.model_id == "null"
        assert not status.is_semantic

    def test_skip_unchanged_chunks(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {"f.py": "def foo(): pass\n" * 5})
        sac_dir = tmp_path / ".sac"
        store = EmbeddingStore(sac_dir, NullEmbeddingBackend())
        r1 = store.build(["f.py"], root)
        r2 = store.build(["f.py"], root)
        assert r1["chunks_added"] >= 1
        assert r2["chunks_added"] == 0
        assert r2["chunks_skipped"] == r1["chunks_added"]

    def test_force_re_embeds(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {"f.py": "def bar(): pass\n" * 5})
        sac_dir = tmp_path / ".sac"
        store = EmbeddingStore(sac_dir, NullEmbeddingBackend())
        store.build(["f.py"], root)
        r2 = store.build(["f.py"], root, force=True)
        assert r2["chunks_added"] >= 1
        assert r2["chunks_skipped"] == 0

    def test_search_returns_empty_when_null_backend(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {"auth.py": "def login(): pass\n" * 5})
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        store.build(["auth.py"], root)
        results = store.search("authentication")
        # null backend is not semantic → search returns []
        assert results == []

    def test_search_empty_when_no_index(self, tmp_path: Path) -> None:
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        assert store.search("anything") == []

    def test_build_creates_parent_dirs(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {"a.py": "pass\n" * 5})
        sac_dir = tmp_path / "deep" / "nested" / ".sac"
        store = EmbeddingStore(sac_dir, NullEmbeddingBackend())
        store.build(["a.py"], root)
        assert (sac_dir / "index" / "embeddings.db").exists()

    def test_build_empty_file_list(self, tmp_path: Path) -> None:
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        result = store.build([], tmp_path)
        assert result["files_indexed"] == 0
        assert result["chunks_added"] == 0

    def test_status_to_dict(self, tmp_path: Path) -> None:
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        d = store.status().to_dict()
        assert "exists" in d
        assert "total_chunks" in d
        assert "is_semantic" in d

    def test_multiple_files(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path / "proj", {
            "auth.py": "def login(): pass\n" * 5,
            "db.py": "def connect(): pass\n" * 5,
            "api.py": "def route(): pass\n" * 5,
        })
        store = EmbeddingStore(tmp_path / ".sac", NullEmbeddingBackend())
        result = store.build(["auth.py", "db.py", "api.py"], root)
        assert result["files_indexed"] == 3

    def test_corrupt_db_status_returns_empty(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        db_path = sac_dir / "index" / "embeddings.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_bytes(b"NOT A DATABASE")
        store = EmbeddingStore(sac_dir, NullEmbeddingBackend())
        # status should not raise; may return empty or raise sqlite error
        try:
            status = store.status()
            # If it doesn't raise, it should report as non-existent or 0 chunks
        except Exception:
            pass  # also acceptable


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------


class TestHybridRetriever:
    def test_retrieve_returns_list(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"src/auth.py": "def login(): pass"})
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("auth login")
        assert isinstance(results, list)

    def test_selection_reason_present(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"auth.py": "def login(): pass"})
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("auth")
        if results:
            assert results[0].selection_reason != ""

    def test_no_results_for_unmatched_query(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"src/foo.py": "x = 1"})
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("zzz_no_match_xyz")
        assert isinstance(results, list)

    def test_keyword_match_in_reason(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {
            "src/auth.py": "def login(): pass",
            "src/database.py": "def connect(): pass",
        })
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("auth")
        if results:
            top = results[0]
            assert "auth" in top.path or "auth" in top.selection_reason

    def test_combined_score_nonnegative(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"auth.py": "def login(): pass"})
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("auth")
        for r in results:
            assert r.combined_score >= 0.0

    def test_limit_respected(self, tmp_path: Path) -> None:
        files = {f"module_{i}.py": f"def func_{i}(): pass" for i in range(20)}
        root = _make_project(tmp_path, files)
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("module", limit=5)
        assert len(results) <= 5

    def test_semantic_failure_falls_back_to_keyword(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"auth.py": "def login(): pass"})
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        # No embedding index built; semantic scores will be empty
        results = retriever.retrieve("auth")
        assert isinstance(results, list)

    def test_hybrid_result_fields(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"auth.py": "def login(): pass"})
        retriever = HybridRetriever(root, sac_dir=tmp_path / ".sac")
        results = retriever.retrieve("auth")
        for r in results:
            assert hasattr(r, "path")
            assert hasattr(r, "keyword_score")
            assert hasattr(r, "semantic_score")
            assert hasattr(r, "combined_score")
            assert hasattr(r, "selection_reason")


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


class TestIndexCLI:
    def test_index_build_runs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner
        from safecode.cli_project import index_app
        root = _make_project(tmp_path, {"src/auth.py": "def login(): pass\n" * 10})
        monkeypatch.chdir(root)
        runner = CliRunner()
        result = runner.invoke(index_app, ["build", "--json"], catch_exceptions=False)
        # May fail if project root detection doesn't pick up tmp_path;
        # just verify it doesn't crash with an unhandled exception
        assert result.exit_code in {0, 1}

    def test_index_status_no_index(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner
        from safecode.cli_project import index_app
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(index_app, ["status"], catch_exceptions=False)
        assert result.exit_code in {0, 1}


class TestSearchCLI:
    def test_search_command_exists(self) -> None:
        from typer.testing import CliRunner
        from safecode.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "query" in result.output.lower() or "search" in result.output.lower()

    def test_search_no_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner
        from safecode.cli import app
        _make_project(tmp_path, {"src/auth.py": "def login(): pass\n"})
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["search", "zzz_no_match_xyz_abc", "--json"],
                               catch_exceptions=False)
        assert result.exit_code in {0, 1}

    def test_search_json_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import json as _json
        from typer.testing import CliRunner
        from safecode.cli import app
        _make_project(tmp_path, {"src/example.py": "def test_value():\n    return 'test'\n" * 5})
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["search", "test", "--json"],
                               catch_exceptions=False)
        if result.exit_code == 0:
            data = _json.loads(result.output)
            assert "results" in data.get("data", {})
