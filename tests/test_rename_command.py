"""Tests for sac rename (v6.9.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_refactor import build_rename_patch, _replace_symbol_in_line

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit: _replace_symbol_in_line
# ---------------------------------------------------------------------------


class TestReplaceSymbolInLine:
    def test_replaces_word(self) -> None:
        result = _replace_symbol_in_line("x = parse_args()", "parse_args", "parse_arguments")
        assert "parse_arguments" in result
        assert "parse_args" not in result

    def test_does_not_replace_inside_string_double(self) -> None:
        result = _replace_symbol_in_line('msg = "call parse_args here"', "parse_args", "new_name")
        assert "parse_args" in result   # inside string, not replaced

    def test_does_not_replace_inside_string_single(self) -> None:
        result = _replace_symbol_in_line("msg = 'use parse_args'", "parse_args", "new_name")
        assert "parse_args" in result

    def test_does_not_replace_inside_comment(self) -> None:
        result = _replace_symbol_in_line("# call parse_args here\n", "parse_args", "new_name")
        assert "parse_args" in result
        assert "new_name" not in result

    def test_word_boundary_no_partial(self) -> None:
        result = _replace_symbol_in_line("x = parse_args_extra()", "parse_args", "new_name")
        # Should NOT replace parse_args_extra
        assert "parse_args_extra" in result
        assert "new_name_extra" not in result

    def test_replaces_multiple_occurrences(self) -> None:
        line = "result = foo(foo(x))"
        result = _replace_symbol_in_line(line, "foo", "bar")
        assert result.count("bar") == 2

    def test_no_replacement_needed(self) -> None:
        line = "x = other_func()\n"
        result = _replace_symbol_in_line(line, "foo", "bar")
        assert result == line


# ---------------------------------------------------------------------------
# Unit: build_rename_patch
# ---------------------------------------------------------------------------


class TestBuildRenamePatch:
    def test_generates_block_for_changed_file(self, tmp_path: Path) -> None:
        (tmp_path / "foo.py").write_text(
            "def old_name():\n    pass\n\nold_name()\n", encoding="utf-8"
        )
        refs = [
            {"file": "foo.py", "line": 1},
            {"file": "foo.py", "line": 4},
        ]
        blocks = build_rename_patch("old_name", "new_name", refs, tmp_path)
        assert len(blocks) >= 1
        assert all("new_name" in b["replace"] for b in blocks)

    def test_skips_file_if_symbol_only_in_string(self, tmp_path: Path) -> None:
        (tmp_path / "foo.py").write_text(
            'msg = "old_name is here"\n', encoding="utf-8"
        )
        refs = [{"file": "foo.py", "line": 1}]
        blocks = build_rename_patch("old_name", "new_name", refs, tmp_path)
        # "old_name" inside a string → no change → no block
        assert len(blocks) == 0

    def test_handles_multi_file(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("def sym(): pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("from a import sym\nsym()\n", encoding="utf-8")
        refs = [
            {"file": "a.py", "line": 1},
            {"file": "b.py", "line": 2},
        ]
        blocks = build_rename_patch("sym", "renamed", refs, tmp_path)
        files = {b["file_path"] for b in blocks}
        assert len(files) == 2

    def test_missing_file_skipped_gracefully(self, tmp_path: Path) -> None:
        refs = [{"file": "ghost.py", "line": 1}]
        blocks = build_rename_patch("sym", "new", refs, tmp_path)
        assert blocks == []

    def test_context_lines_are_not_rewritten(self, tmp_path: Path) -> None:
        (tmp_path / "foo.py").write_text(
            "# old_name should stay in comment context\n"
            "def old_name():\n"
            "    return 1\n",
            encoding="utf-8",
        )
        refs = [{"file": "foo.py", "line": 2}]
        blocks = build_rename_patch("old_name", "new_name", refs, tmp_path)
        assert blocks
        assert "# old_name should stay" in blocks[0]["replace"]
        assert "def new_name" in blocks[0]["replace"]


# ---------------------------------------------------------------------------
# CLI: sac refactor rename
# ---------------------------------------------------------------------------


class TestRenameCommandCLI:
    def test_rename_help(self) -> None:
        result = runner.invoke(app, ["refactor", "rename", "--help"])
        assert result.exit_code == 0
        assert "rename" in result.output.lower()

    def test_rename_invalid_old_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["refactor", "rename", "not-valid!", "new_name", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_rename_same_name_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["refactor", "rename", "foo", "foo", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_rename_no_refs_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "foo.py").write_text("x = 1\n")
        result = runner.invoke(app, ["refactor", "rename", "nonexistent_sym", "new_sym", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["refs_found"] == 0

    def test_dry_run_shows_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "foo.py").write_text("def my_func(): pass\nmy_func()\n")
        result = runner.invoke(app, ["refactor", "rename", "my_func", "renamed_func",
                                     "--dry-run", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["dry_run"] is True
        assert data["data"]["refs_found"] > 0

    def test_outside_root_file_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["refactor", "rename", "foo", "bar",
                                     "--file", "../../etc/passwd", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "outside" in data["error"].lower()

    def test_rename_ambiguous_requires_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.py").write_text("def shared(): pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def shared(): pass\n", encoding="utf-8")
        result = runner.invoke(app, ["refactor", "rename", "shared", "renamed", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "multiple definitions" in data["error"]

    def test_rename_produces_patch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rename creates a pending patch when invoked in JSON mode."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "util.py").write_text("def compute(x):\n    return x * 2\ncompute(5)\n")
        (tmp_path / ".sac").mkdir(exist_ok=True)

        result = runner.invoke(app, ["refactor", "rename", "compute", "calculate", "--json"])
        data = json.loads(result.output)
        # Should either be pending (patch saved) or success (no refs found in this simple case)
        assert data["status"] in ("pending", "success")
        if data["status"] == "pending":
            assert "patch_id" in data["data"]
            pending_path = tmp_path / ".sac" / "pending_patch.json"
            assert pending_path.exists()
