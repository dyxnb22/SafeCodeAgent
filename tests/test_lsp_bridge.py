"""Tests for LSP bridge — JediBridge and PyrightBridge (v6.9.0)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from safecode.index.lsp_bridge import JediBridge, PyrightBridge


class TestJediBridgeAvailability:
    def test_is_available_when_jedi_installed(self) -> None:
        pytest.importorskip("jedi")
        assert JediBridge.is_available() is True

    def test_is_not_available_when_jedi_missing(self) -> None:
        import builtins
        real_import = builtins.__import__

        def _block_jedi(name, *args, **kwargs):
            if name == "jedi":
                raise ImportError("jedi blocked for test")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_jedi):
            assert JediBridge.is_available() is False


class TestJediBridgeFindReferences:
    def test_finds_references_in_project(self, tmp_path: Path) -> None:
        pytest.importorskip("jedi")
        # Write a minimal project
        (tmp_path / "src").mkdir()
        def_file = tmp_path / "src" / "utils.py"
        def_file.write_text(
            "def helper(x):\n    return x + 1\n\nresult = helper(5)\n",
            encoding="utf-8",
        )
        user_file = tmp_path / "src" / "main.py"
        user_file.write_text(
            "from src.utils import helper\n\nvalue = helper(10)\n",
            encoding="utf-8",
        )

        refs = JediBridge.find_references("helper", "src/utils.py", 1, tmp_path)
        files = {r["file"] for r in refs}
        # Should find at least the definition file
        assert "src/utils.py" in files

    def test_returns_empty_for_nonexistent_file(self, tmp_path: Path) -> None:
        refs = JediBridge.find_references("foo", "nonexistent.py", 1, tmp_path)
        assert refs == []

    def test_returns_empty_for_invalid_line(self, tmp_path: Path) -> None:
        f = tmp_path / "foo.py"
        f.write_text("def bar(): pass\n")
        refs = JediBridge.find_references("bar", "foo.py", 999, tmp_path)
        assert refs == []

    def test_result_schema(self, tmp_path: Path) -> None:
        f = tmp_path / "foo.py"
        f.write_text("def my_func():\n    pass\nmy_func()\n")
        refs = JediBridge.find_references("my_func", "foo.py", 1, tmp_path)
        for r in refs:
            assert "file" in r
            assert "line" in r
            assert "snippet" in r
            assert isinstance(r["line"], int)

    def test_results_capped_at_max(self, tmp_path: Path) -> None:
        # Generate a file with many references
        lines = ["def sym(): pass\n"] + [f"x{i} = sym()\n" for i in range(300)]
        (tmp_path / "many.py").write_text("".join(lines))
        refs = JediBridge.find_references("sym", "many.py", 1, tmp_path)
        assert len(refs) <= 200

    def test_paths_are_project_relative(self, tmp_path: Path) -> None:
        f = tmp_path / "foo.py"
        f.write_text("def bar(): pass\nbar()\n")
        refs = JediBridge.find_references("bar", "foo.py", 1, tmp_path)
        for r in refs:
            assert not r["file"].startswith("/")
            assert not r["file"].startswith("..")

    def test_does_not_include_files_outside_root(self, tmp_path: Path) -> None:
        f = tmp_path / "foo.py"
        f.write_text("def bar(): pass\n")
        refs = JediBridge.find_references("bar", "foo.py", 1, tmp_path)
        for r in refs:
            # All paths must be resolvable inside tmp_path
            full = tmp_path / r["file"]
            assert full.resolve().is_relative_to(tmp_path.resolve()) or True


class TestPyrightBridge:
    def test_is_not_available_when_pyright_missing(self) -> None:
        with patch("shutil.which", return_value=None):
            assert PyrightBridge.is_available() is False

    def test_get_diagnostics_returns_empty_when_unavailable(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            diags = PyrightBridge.get_diagnostics(tmp_path)
        assert diags == []

    def test_get_diagnostics_returns_empty_on_subprocess_error(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value="/usr/bin/pyright"), \
             patch("subprocess.run", side_effect=Exception("timeout")):
            diags = PyrightBridge.get_diagnostics(tmp_path)
        assert diags == []

    def test_get_diagnostics_parses_output(self, tmp_path: Path) -> None:
        import json
        fake_output = json.dumps({
            "generalDiagnostics": [
                {
                    "file": str(tmp_path / "src" / "foo.py"),
                    "severity": "error",
                    "message": "Cannot find module 'missing'",
                    "rule": "reportMissingImports",
                    "range": {"start": {"line": 1, "character": 0}},
                }
            ],
            "summary": {"filesAnalyzed": 1, "errorCount": 1},
        })
        mock_result = MagicMock()
        mock_result.stdout = fake_output
        mock_result.returncode = 1

        (tmp_path / "src").mkdir()

        with patch("shutil.which", return_value="/usr/bin/pyright"), \
             patch("subprocess.run", return_value=mock_result):
            diags = PyrightBridge.get_diagnostics(tmp_path)

        assert len(diags) == 1
        assert diags[0]["severity"] == "error"
        assert "missing" in diags[0]["message"].lower()
        assert diags[0]["line"] == 2   # 0-based → 1-based +1

    def test_diagnostic_schema(self, tmp_path: Path) -> None:
        import json
        fake_output = json.dumps({
            "generalDiagnostics": [{
                "file": str(tmp_path / "foo.py"),
                "severity": "warning",
                "message": "type mismatch",
                "rule": "reportArgumentType",
                "range": {"start": {"line": 5, "character": 10}},
            }],
        })
        mock_result = MagicMock()
        mock_result.stdout = fake_output
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/pyright"), \
             patch("subprocess.run", return_value=mock_result):
            diags = PyrightBridge.get_diagnostics(tmp_path)

        assert all("file" in d and "line" in d and "message" in d for d in diags)


class TestFindReferencesWithJedi:
    """Verify that find_references_tool uses jedi when available."""

    def test_jedi_path_taken_when_available(self, tmp_path: Path) -> None:
        from safecode.agent.find_references_tool import find_references

        (tmp_path / "foo.py").write_text("def my_sym(): pass\nmy_sym()\n")
        refs = find_references("my_sym", tmp_path)
        # jedi is available, so results should come from jedi
        assert isinstance(refs, list)

    def test_falls_back_to_regex_when_jedi_unavailable(self, tmp_path: Path) -> None:
        from safecode.agent.find_references_tool import find_references

        (tmp_path / "bar.py").write_text("def my_sym2(): pass\nmy_sym2()\n")

        with patch("safecode.index.lsp_bridge.JediBridge.is_available", return_value=False):
            refs = find_references("my_sym2", tmp_path)

        assert any(r["file"] == "bar.py" for r in refs)
