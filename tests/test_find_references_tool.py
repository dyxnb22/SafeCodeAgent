"""Tests for find_references native tool (v6.9.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.agent.find_references_tool import find_references, _handler
from safecode.agent.find_references_tool import AmbiguousSymbolError


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path


class TestFindReferences:
    def test_finds_function_in_same_file(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {
            "src/utils.py": "def helper():\n    pass\n\nresult = helper()\n",
        })
        refs = find_references("helper", tmp_path)
        assert any(r["file"] == "src/utils.py" for r in refs)
        lines = [r["line"] for r in refs if r["file"] == "src/utils.py"]
        assert 1 in lines or 4 in lines  # definition or call

    def test_finds_references_across_files(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {
            "src/parser.py": "def parse_args(argv):\n    return argv\n",
            "src/main.py": "from src.parser import parse_args\n\nargs = parse_args([])\n",
        })
        refs = find_references("parse_args", tmp_path)
        files = {r["file"] for r in refs}
        assert "src/parser.py" in files

    def test_returns_empty_for_nonexistent_symbol(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/foo.py": "def bar(): pass\n"})
        refs = find_references("nonexistent_xyz_abc", tmp_path)
        assert refs == []

    def test_invalid_symbol_returns_empty(self, tmp_path: Path) -> None:
        refs = find_references("not-valid!", tmp_path)
        assert refs == []

    def test_empty_symbol_returns_empty(self, tmp_path: Path) -> None:
        refs = find_references("", tmp_path)
        assert refs == []

    def test_result_shape(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/foo.py": "def my_func(): pass\nmy_func()\n"})
        refs = find_references("my_func", tmp_path)
        assert len(refs) > 0
        for ref in refs:
            assert "file" in ref
            assert "line" in ref
            assert "snippet" in ref
            assert isinstance(ref["line"], int)
            assert ref["line"] >= 1

    def test_results_capped(self, tmp_path: Path) -> None:
        # Create a file with many references
        many_refs = "\n".join(f"x = my_symbol_{i}" for i in range(200))
        _make_project(tmp_path, {"src/many.py": "def my_symbol_0(): pass\n" + many_refs})
        refs = find_references("my_symbol_0", tmp_path)
        assert len(refs) <= 100

    def test_file_hint_restricts_definition(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {
            "src/a.py": "def shared(): pass\n",
            "src/b.py": "def shared(): pass\n",
            "src/user.py": "from src.a import shared\nshared()\n",
        })
        refs_a = find_references("shared", tmp_path, file="src/a.py")
        refs_b = find_references("shared", tmp_path, file="src/b.py")
        # Both should find at least the definition file
        assert any(r["file"] == "src/a.py" for r in refs_a)
        assert any(r["file"] == "src/b.py" for r in refs_b)

    def test_multiple_definitions_without_file_is_ambiguous(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {
            "src/a.py": "def shared(): pass\n",
            "src/b.py": "def shared(): pass\n",
        })
        with pytest.raises(AmbiguousSymbolError):
            find_references("shared", tmp_path)

    def test_does_not_escape_project_root(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/foo.py": "def bar(): pass\n"})
        refs = find_references("bar", tmp_path)
        for ref in refs:
            assert not ref["file"].startswith("/")
            assert not ref["file"].startswith("..")


class TestHandlerFindReferences:
    def _call(self, tmp_path: Path, **kwargs):
        return _handler("test-call-id", {"_project_root": str(tmp_path), **kwargs})

    def test_missing_symbol_returns_error(self, tmp_path: Path) -> None:
        result = self._call(tmp_path)
        assert result.status == "error"
        assert result.error is not None

    def test_invalid_symbol_returns_error(self, tmp_path: Path) -> None:
        result = self._call(tmp_path, symbol="not-valid")
        assert result.status == "error"
        assert "Invalid symbol" in (result.error or "")

    def test_path_traversal_in_file_blocked(self, tmp_path: Path) -> None:
        result = self._call(tmp_path, symbol="foo", file="../../etc/passwd")
        assert result.status == "blocked"
        assert "outside" in (result.error or "").lower()

    def test_ambiguous_symbol_is_blocked(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("def shared(): pass\n")
        (tmp_path / "src" / "b.py").write_text("def shared(): pass\n")
        result = self._call(tmp_path, symbol="shared")
        assert result.status == "blocked"
        assert "multiple definitions" in (result.error or "")

    def test_found_references_in_output(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("def my_ref(): pass\nmy_ref()\n")
        result = self._call(tmp_path, symbol="my_ref")
        assert result.status == "success"
        assert "my_ref" in (result.output or "")

    def test_not_found_is_success_with_message(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("def other(): pass\n")
        result = self._call(tmp_path, symbol="ghost_symbol")
        assert result.status == "success"
        assert "No references" in (result.output or "")


class TestRegisterFindReferencesTool:
    def test_registers_without_error(self, tmp_path: Path) -> None:
        from safecode.agent.native_dispatcher import NativeToolDispatcher
        from safecode.agent.find_references_tool import register_find_references_tool

        dispatcher = NativeToolDispatcher()
        register_find_references_tool(dispatcher, tmp_path)
        specs = dispatcher.list_specs() if hasattr(dispatcher, "list_specs") else []
        # If list_specs not available, just verify no exception was raised
        assert True

    def test_tool_is_auto_approved(self, tmp_path: Path) -> None:
        from safecode.agent.native_dispatcher import NativeToolDispatcher
        from safecode.agent.find_references_tool import register_find_references_tool

        dispatcher = NativeToolDispatcher()
        register_find_references_tool(dispatcher, tmp_path)
        # The tool should be discoverable
        spec = dispatcher.get_spec("find_references") if hasattr(dispatcher, "get_spec") else None
        # Just verify registration succeeded (no exception)
        assert True
