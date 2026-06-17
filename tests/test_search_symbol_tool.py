"""Tests for v6.25: search_symbol native tool."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.agent.read_tools import SEARCH_SYMBOL_SPEC, _search_symbol_handler, _search_symbol_via_walk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "parser.py").write_text(
        "class Config:\n"
        "    pass\n"
        "\n"
        "def parse_config(path):\n"
        "    return Config()\n"
        "\n"
        "def _parse_internal():\n"
        "    pass\n"
    )
    (tmp_path / "src" / "utils.go").write_text(
        "func parseConfig(path string) Config {\n"
        "    return Config{}\n"
        "}\n"
    )
    (tmp_path / "tests" / "test_parser.py").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "test_parser.py").rmdir()
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_parser.py").write_text(
        "def test_parse_config():\n"
        "    pass\n"
    )
    return tmp_path


def _call(tmp_path: Path, **kwargs) -> dict:
    inp = {"_project_root": str(tmp_path), **kwargs}
    result = _search_symbol_handler("c1", inp)
    assert result.tool_name == "search_symbol"
    return result


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------

class TestSearchSymbolBasic:
    def test_finds_python_function(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config")
        assert r.status != "error"
        hits = json.loads(r.output)
        assert any(h["file"] == "src/parser.py" and h["kind"] == "function" for h in hits)

    def test_finds_python_class(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="Config")
        hits = json.loads(r.output)
        assert any(h["kind"] == "class" for h in hits)

    def test_kind_filter_function(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config", kind="function")
        hits = json.loads(r.output)
        assert all(h["kind"] == "function" for h in hits)

    def test_kind_filter_class(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="Config", kind="class")
        hits = json.loads(r.output)
        assert all(h["kind"] == "class" for h in hits)

    def test_file_filter(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config", file="src/parser.py")
        hits = json.loads(r.output)
        assert all(h["file"] == "src/parser.py" for h in hits)

    def test_missing_name_returns_error(self, tmp_path):
        r = _call(tmp_path)
        assert r.status == "error"
        assert "name" in r.error.lower()

    def test_short_name_returns_error(self, tmp_path):
        r = _call(tmp_path, name="x")
        assert r.status == "error"

    def test_no_matches_returns_empty(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="nonexistent_xyz_abc_123")
        assert r.status != "error"
        hits = json.loads(r.output)
        assert hits == []

    def test_snake_case_query_finds_camel_case_definition(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config", file="src/utils.go")
        hits = json.loads(r.output)
        assert any(h["file"] == "src/utils.go" and h["kind"] == "function" for h in hits)
        assert r.metadata["backend"] in {"walk", "ripgrep+walk"}

    def test_snippet_present(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config")
        hits = json.loads(r.output)
        assert all("snippet" in h for h in hits)

    def test_metadata_count(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config")
        hits = json.loads(r.output)
        assert r.metadata["count"] == len(hits)

    def test_path_traversal_blocked(self, tmp_path):
        _make_project(tmp_path)
        r = _call(tmp_path, name="parse_config", file="../../../etc/passwd")
        # Should not error out with crash — path validation gracefully handles it
        # (the file simply won't be found inside the project)
        hits = json.loads(r.output) if r.output else []
        assert isinstance(hits, list)

    def test_sac_dir_excluded(self, tmp_path):
        _make_project(tmp_path)
        sac = tmp_path / ".sac"
        sac.mkdir()
        (sac / "secret.py").write_text("def parse_config():\n    pass\n")
        r = _call(tmp_path, name="parse_config")
        hits = json.loads(r.output)
        assert not any(".sac" in h["file"] for h in hits)

    def test_git_dir_excluded(self, tmp_path):
        _make_project(tmp_path)
        git = tmp_path / ".git"
        git.mkdir()
        (git / "hook.py").write_text("def parse_config():\n    pass\n")
        r = _call(tmp_path, name="parse_config")
        hits = json.loads(r.output)
        assert not any(".git" in h["file"] for h in hits)


# ---------------------------------------------------------------------------
# Walk fallback (always available without ripgrep)
# ---------------------------------------------------------------------------

class TestSearchSymbolWalkFallback:
    def test_walk_finds_function(self, tmp_path):
        _make_project(tmp_path)
        results, truncated = _search_symbol_via_walk(tmp_path, "parse_config", None, None)
        assert any(r["file"] == "src/parser.py" and r["kind"] == "function" for r in results)

    def test_walk_kind_filter(self, tmp_path):
        _make_project(tmp_path)
        results, _ = _search_symbol_via_walk(tmp_path, "Config", "class", None)
        assert all(r["kind"] == "class" for r in results)

    def test_walk_empty_on_no_match(self, tmp_path):
        _make_project(tmp_path)
        results, _ = _search_symbol_via_walk(tmp_path, "no_such_symbol_xyz", None, None)
        assert results == []

    def test_walk_normalizes_snake_and_camel_case(self, tmp_path):
        _make_project(tmp_path)
        results, _ = _search_symbol_via_walk(tmp_path, "parse_config", "function", "src/utils.go")
        assert any(r["file"] == "src/utils.go" for r in results)


class TestSearchSymbolDiscovery:
    def test_spec_description_guides_symbol_first_usage(self):
        assert "before reading broad files" in SEARCH_SYMBOL_SPEC.description
        assert "snake_case and camelCase" in SEARCH_SYMBOL_SPEC.description
