"""Tests for read-only native tools (v4.20.1, EXPERIMENTAL)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.agent.read_tools import (
    _read_file_handler,
    _list_files_handler,
    _search_files_handler,
    _grep_files_handler,
    register_read_tools,
    READ_FILE_SPEC,
    LIST_FILES_SPEC,
    SEARCH_FILES_SPEC,
    GREP_FILES_SPEC,
)
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall


def _inp(project_root: Path, **kwargs):
    return {"_project_root": str(project_root), **kwargs}


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def test_read_file_success(tmp_path: Path):
    f = tmp_path / "hello.py"
    f.write_text("x = 1\ny = 2\n")
    result = _read_file_handler("c1", _inp(tmp_path, path="hello.py"))
    assert result.status == "success"
    assert "x = 1" in result.output
    assert result.metadata["returned_lines"] == 2


def test_read_file_missing_file(tmp_path: Path):
    result = _read_file_handler("c1", _inp(tmp_path, path="no_such.py"))
    assert result.status == "error"
    assert "not found" in result.error.lower()


def test_read_file_root_escape_blocked(tmp_path: Path):
    result = _read_file_handler("c1", _inp(tmp_path, path="../../etc/passwd"))
    assert result.status == "blocked"
    assert "outside" in result.error.lower()


def test_read_file_sensitive_blocked(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=abc")
    result = _read_file_handler("c1", _inp(tmp_path, path=".env"))
    assert result.status == "blocked"


def test_read_file_redacts_secrets(tmp_path: Path):
    f = tmp_path / "config.py"
    f.write_text("API_KEY=my_very_secret_key_12345\n")
    result = _read_file_handler("c1", _inp(tmp_path, path="config.py"))
    assert result.status == "success"
    assert "my_very_secret_key_12345" not in result.output


def test_read_file_line_range(tmp_path: Path):
    f = tmp_path / "lines.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 20)))
    result = _read_file_handler("c1", _inp(tmp_path, path="lines.txt", start_line=3, end_line=5))
    assert result.status == "success"
    assert "line 3" in result.output
    assert "line 1" not in result.output


def test_read_file_caps_at_400_lines(tmp_path: Path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 1001)))
    result = _read_file_handler("c1", _inp(tmp_path, path="big.txt"))
    assert result.metadata["returned_lines"] == 400
    assert result.metadata.get("truncated") is True


def test_read_file_missing_path_arg(tmp_path: Path):
    result = _read_file_handler("c1", _inp(tmp_path))
    assert result.status == "error"
    assert "path" in result.error.lower()


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

def test_list_files_basic(tmp_path: Path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("y")
    result = _list_files_handler("c1", _inp(tmp_path, path="."))
    assert result.status == "success"
    assert "a.py" in result.output
    assert "b.py" in result.output


def test_list_files_skips_git_dir(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (tmp_path / "src.py").write_text("x")
    result = _list_files_handler("c1", _inp(tmp_path, path="."))
    assert ".git" not in result.output
    assert "src.py" in result.output


def test_list_files_non_recursive(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("x")
    (tmp_path / "top.py").write_text("y")
    result = _list_files_handler("c1", _inp(tmp_path, path=".", recursive=False))
    assert "top.py" in result.output
    assert "deep.py" not in result.output


def test_list_files_root_escape_blocked(tmp_path: Path):
    result = _list_files_handler("c1", _inp(tmp_path, path="../../"))
    assert result.status == "blocked"


def test_list_files_truncated_flag(tmp_path: Path):
    for i in range(10):
        (tmp_path / f"f{i}.py").write_text(f"x={i}")
    from safecode.agent import read_tools
    original_cap = read_tools._MAX_LIST_FILES
    read_tools._MAX_LIST_FILES = 3
    try:
        result = _list_files_handler("c1", _inp(tmp_path, path="."))
        assert result.metadata["truncated"] is True
        assert result.metadata["count"] == 3
    finally:
        read_tools._MAX_LIST_FILES = original_cap


# ---------------------------------------------------------------------------
# search_files
# ---------------------------------------------------------------------------

def test_search_files_finds_match(tmp_path: Path):
    (tmp_path / "foo.py").write_text("def hello_world():\n    pass\n")
    result = _search_files_handler("c1", _inp(tmp_path, pattern="hello_world"))
    assert result.status == "success"
    hits = json.loads(result.output)
    assert len(hits) == 1
    assert hits[0]["file"] == "foo.py"
    assert hits[0]["line"] == 1


def test_search_files_missing_pattern(tmp_path: Path):
    result = _search_files_handler("c1", _inp(tmp_path))
    assert result.status == "error"
    assert "pattern" in result.error.lower()


def test_search_files_skips_sensitive(tmp_path: Path):
    (tmp_path / ".env").write_text("SECRET=mysecret\npattern_here=x")
    result = _search_files_handler("c1", _inp(tmp_path, pattern="pattern_here"))
    hits = json.loads(result.output)
    assert len(hits) == 0


def test_search_files_include_glob(tmp_path: Path):
    (tmp_path / "a.py").write_text("needle in python")
    (tmp_path / "b.txt").write_text("needle in text")
    result = _search_files_handler("c1", _inp(tmp_path, pattern="needle", include_glob="*.py"))
    hits = json.loads(result.output)
    assert all(h["file"].endswith(".py") for h in hits)


def test_search_files_redacts_secrets(tmp_path: Path):
    (tmp_path / "cfg.py").write_text("API_KEY=supersecret123\nfind_me=here")
    result = _search_files_handler("c1", _inp(tmp_path, pattern="supersecret123"))
    hits = json.loads(result.output)
    for h in hits:
        assert "supersecret123" not in h["content"]


# ---------------------------------------------------------------------------
# grep_files
# ---------------------------------------------------------------------------

def test_grep_files_regex_match(tmp_path: Path):
    (tmp_path / "src.py").write_text("def foo_bar():\n    return 42\n")
    result = _grep_files_handler("c1", _inp(tmp_path, regex=r"def \w+"))
    assert result.status == "success"
    hits = json.loads(result.output)
    assert any("foo_bar" in h["content"] for h in hits)


def test_grep_files_invalid_regex(tmp_path: Path):
    result = _grep_files_handler("c1", _inp(tmp_path, regex="[unclosed"))
    assert result.status == "error"
    assert "regex" in result.error.lower()


def test_grep_files_case_insensitive(tmp_path: Path):
    (tmp_path / "t.py").write_text("Hello World")
    result = _grep_files_handler("c1", _inp(tmp_path, regex="hello", case_insensitive=True))
    hits = json.loads(result.output)
    assert len(hits) == 1


def test_grep_files_missing_regex(tmp_path: Path):
    result = _grep_files_handler("c1", _inp(tmp_path))
    assert result.status == "error"


# ---------------------------------------------------------------------------
# register_read_tools integration
# ---------------------------------------------------------------------------

def test_register_read_tools_wires_four_tools(tmp_path: Path):
    dispatcher = NativeToolDispatcher()
    register_read_tools(dispatcher, tmp_path)
    names = {s.name for s in dispatcher.specs()}
    # v6.25 added search_symbol as a 5th read tool.
    assert {"read_file", "list_files", "search_files", "grep_files"}.issubset(names)
    assert "search_symbol" in names


def test_registered_read_file_works(tmp_path: Path):
    (tmp_path / "hello.txt").write_text("registered tool works!")
    dispatcher = NativeToolDispatcher()
    register_read_tools(dispatcher, tmp_path)
    call = NativeToolCall(tool_name="read_file", input={"path": "hello.txt"}, call_id="c1")
    result = dispatcher.dispatch(call)
    assert result.status == "success"
    assert "registered tool works!" in result.output
