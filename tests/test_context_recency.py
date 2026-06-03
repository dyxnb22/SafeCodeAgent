"""Tests for ContextSelector git-recency signal (v3.7.2 T-3.7.2-A)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.context.selector import (
    ContextSelector,
    SelectedContextSource,
    _RecencyCache,
    _RECENCY_BONUS,
    _get_head,
    _get_recent_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_selector_with_recent(
    project_root: Path,
    recent: set[str],
) -> ContextSelector:
    """Return a ContextSelector whose _recent_files() is stubbed to return ``recent``."""
    sel = ContextSelector(project_root)
    frozen = frozenset(recent)
    sel._recent_files = lambda: frozen  # type: ignore[method-assign]
    return sel


def _index_files(tmp_path: Path, files: list[str]) -> None:
    """Create stub files in tmp_path."""
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# stub\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit: _get_recent_files
# ---------------------------------------------------------------------------

class TestGetRecentFiles:
    def test_returns_frozenset(self, tmp_path: Path) -> None:
        with patch("safecode.context.selector.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            result = _get_recent_files(tmp_path)
        assert isinstance(result, frozenset)

    def test_parses_git_log_output(self, tmp_path: Path) -> None:
        git_output = "\nsrc/foo.py\nREADME.md\n\nsrc/bar.py\n"
        with patch("safecode.context.selector.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = git_output
            result = _get_recent_files(tmp_path)
        assert "src/foo.py" in result
        assert "README.md" in result
        assert "src/bar.py" in result
        # Also contains basenames
        assert "foo.py" in result
        assert "bar.py" in result

    def test_returns_empty_on_nonzero_exit(self, tmp_path: Path) -> None:
        with patch("safecode.context.selector.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 128
            mock_run.return_value.stdout = "some output"
            result = _get_recent_files(tmp_path)
        assert len(result) == 0

    def test_returns_empty_on_oserror(self, tmp_path: Path) -> None:
        with patch("safecode.context.selector.subprocess.run", side_effect=OSError):
            result = _get_recent_files(tmp_path)
        assert len(result) == 0

    def test_returns_empty_on_timeout(self, tmp_path: Path) -> None:
        import subprocess
        with patch("safecode.context.selector.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            result = _get_recent_files(tmp_path)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Unit: _get_head
# ---------------------------------------------------------------------------

class TestGetHead:
    def test_returns_hash_string(self, tmp_path: Path) -> None:
        with patch("safecode.context.selector.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "deadbeef123\n"
            result = _get_head(tmp_path)
        assert result == "deadbeef123"

    def test_returns_empty_string_on_error(self, tmp_path: Path) -> None:
        with patch("safecode.context.selector.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 128
            mock_run.return_value.stdout = ""
            result = _get_head(tmp_path)
        assert result == ""

    def test_returns_empty_on_oserror(self, tmp_path: Path) -> None:
        with patch("safecode.context.selector.subprocess.run", side_effect=OSError):
            result = _get_head(tmp_path)
        assert result == ""


# ---------------------------------------------------------------------------
# Unit: recency cache invalidation
# ---------------------------------------------------------------------------

class TestRecencyCacheInvalidation:
    def test_cache_hit_returns_same_frozenset(self, tmp_path: Path) -> None:
        sel = ContextSelector(tmp_path)
        recent = frozenset({"foo.py", "bar.py"})
        sel._recency_cache = _RecencyCache(head="abc", recent_files=recent)

        with patch("safecode.context.selector._get_head", return_value="abc"):
            result = sel._recent_files()
        assert result is recent

    def test_cache_miss_refreshes_on_new_head(self, tmp_path: Path) -> None:
        sel = ContextSelector(tmp_path)
        sel._recency_cache = _RecencyCache(head="old", recent_files=frozenset({"old.py"}))

        with (
            patch("safecode.context.selector._get_head", return_value="new"),
            patch("safecode.context.selector._get_recent_files", return_value=frozenset({"new.py"})),
        ):
            result = sel._recent_files()
        assert "new.py" in result
        assert "old.py" not in result

    def test_empty_head_still_refreshes_cache(self, tmp_path: Path) -> None:
        sel = ContextSelector(tmp_path)
        with (
            patch("safecode.context.selector._get_head", return_value=""),
            patch("safecode.context.selector._get_recent_files", return_value=frozenset({"x.py"})),
        ):
            result = sel._recent_files()
        assert "x.py" in result


# ---------------------------------------------------------------------------
# Integration: recency boosts score without being the sole signal
# ---------------------------------------------------------------------------

class TestRecencyScoreBoost:
    def test_recent_file_gets_higher_score(self, tmp_path: Path) -> None:
        _index_files(tmp_path, ["src/foo.py", "src/bar.py"])
        sel = _make_selector_with_recent(tmp_path, recent={"src/foo.py", "foo.py"})

        with patch("safecode.context.selector.FileIndexer") as MockIdx:
            from safecode.index.files import IndexedFile
            MockIdx.return_value.index.return_value = [
                IndexedFile(path="src/foo.py", suffix=".py"),
                IndexedFile(path="src/bar.py", suffix=".py"),
            ]
            sources = sel.select_sources("foo bar")

        foo = next((s for s in sources if "foo" in s.path), None)
        bar = next((s for s in sources if "bar" in s.path), None)
        assert foo is not None
        assert bar is not None
        # foo matches "foo" token AND is recent; bar matches "bar" only
        # foo's total score should be at least bar's
        assert foo.score >= bar.score

    def test_recency_is_additive_not_sole(self, tmp_path: Path) -> None:
        """A file with no keyword match is NOT returned even if it's recent."""
        sel = _make_selector_with_recent(tmp_path, recent={"unrelated.py"})

        with patch("safecode.context.selector.FileIndexer") as MockIdx:
            from safecode.index.files import IndexedFile
            MockIdx.return_value.index.return_value = [
                IndexedFile(path="src/foo.py", suffix=".py"),
                IndexedFile(path="unrelated.py", suffix=".py"),
            ]
            sources = sel.select_sources("foo")

        paths = [s.path for s in sources]
        # "foo.py" matches keyword; "unrelated.py" does not — recency alone doesn't include it
        assert "src/foo.py" in paths
        assert "unrelated.py" not in paths

    def test_recency_reason_appended_to_path_match(self, tmp_path: Path) -> None:
        sel = _make_selector_with_recent(tmp_path, recent={"foo.py"})

        with patch("safecode.context.selector.FileIndexer") as MockIdx:
            from safecode.index.files import IndexedFile
            MockIdx.return_value.index.return_value = [
                IndexedFile(path="src/foo.py", suffix=".py"),
            ]
            sources = sel.select_sources("foo")

        assert sources
        assert "recently modified" in sources[0].reason

    def test_score_bonus_value(self, tmp_path: Path) -> None:
        sel = _make_selector_with_recent(tmp_path, recent={"foo.py"})

        with patch("safecode.context.selector.FileIndexer") as MockIdx:
            from safecode.index.files import IndexedFile
            MockIdx.return_value.index.return_value = [
                IndexedFile(path="src/foo.py", suffix=".py"),
                IndexedFile(path="src/bar.py", suffix=".py"),
            ]
            sources = sel.select_sources("foo bar")

        foo = next(s for s in sources if "foo" in s.path)
        bar = next(s for s in sources if "bar" in s.path)
        # Both match one token; foo also gets recency bonus
        assert foo.score - bar.score == _RECENCY_BONUS

    def test_select_returns_paths_only(self, tmp_path: Path) -> None:
        sel = _make_selector_with_recent(tmp_path, recent=set())
        with patch("safecode.context.selector.FileIndexer") as MockIdx:
            from safecode.index.files import IndexedFile
            MockIdx.return_value.index.return_value = [
                IndexedFile(path="src/main.py", suffix=".py"),
            ]
            paths = sel.select("main")
        assert paths == ["src/main.py"]

    def test_no_regression_when_git_not_available(self, tmp_path: Path) -> None:
        """ContextSelector works even when git is not available."""
        sel = ContextSelector(tmp_path)
        with (
            patch("safecode.context.selector.subprocess.run", side_effect=OSError),
            patch("safecode.context.selector.FileIndexer") as MockIdx,
        ):
            from safecode.index.files import IndexedFile
            MockIdx.return_value.index.return_value = [
                IndexedFile(path="src/foo.py", suffix=".py"),
            ]
            sources = sel.select_sources("foo")
        assert sources
        assert sources[0].path == "src/foo.py"
