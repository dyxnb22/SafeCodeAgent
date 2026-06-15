"""Tests for native tool protocol (v4.20.0, EXPERIMENTAL)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.agent.native_tools import NativeToolCall, NativeToolResult, NativeToolSpec
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.schemas import AgentNativeToolCallResponse, validate_provider_json
from safecode.context.budget import (
    TOKEN_CHAR_RATIO,
    _CODE_TOKEN_CHAR_RATIO,
    ContextBudget,
    ContextBudgetPacker,
    estimate_tokens_from_bytes,
)
from safecode.context.collector import ContextCollector
from safecode.config import SafeCodeConfig


# ---------------------------------------------------------------------------
# NativeToolSpec
# ---------------------------------------------------------------------------

def test_native_tool_spec_defaults():
    spec = NativeToolSpec(name="read_file", description="Read a file.")
    assert spec.name == "read_file"
    assert spec.requires_approval is False
    assert spec.audit_event_type == "tool_call_read"
    assert spec.experimental is True


def test_native_tool_spec_write_requires_approval():
    spec = NativeToolSpec(
        name="edit_file",
        description="Edit a file.",
        requires_approval=True,
        audit_event_type="tool_call_write",
    )
    assert spec.requires_approval is True
    assert spec.audit_event_type == "tool_call_write"


# ---------------------------------------------------------------------------
# NativeToolCall
# ---------------------------------------------------------------------------

def test_native_tool_call_parse():
    call = NativeToolCall(tool_name="read_file", input={"path": "src/foo.py"}, call_id="c1")
    assert call.type == "native_tool_call"
    assert call.tool_name == "read_file"
    assert call.input["path"] == "src/foo.py"


def test_native_tool_call_empty_input():
    call = NativeToolCall(tool_name="list_files")
    assert call.input == {}
    assert call.call_id == ""


# ---------------------------------------------------------------------------
# NativeToolResult
# ---------------------------------------------------------------------------

def test_native_tool_result_success():
    result = NativeToolResult(call_id="c1", tool_name="read_file", output="hello")
    assert result.status == "success"
    assert result.error is None


def test_native_tool_result_blocked():
    result = NativeToolResult(call_id="c2", tool_name="edit_file", status="blocked", error="requires approval")
    assert result.status == "blocked"


def test_native_tool_result_to_context_block():
    result = NativeToolResult(call_id="c1", tool_name="read_file", output="contents")
    block = result.to_context_block()
    assert "[tool:read_file]" in block
    assert "contents" in block


def test_native_tool_result_error_block():
    result = NativeToolResult(call_id="c1", tool_name="read_file", status="error", error="not found")
    block = result.to_context_block()
    assert "error" in block
    assert "not found" in block


# ---------------------------------------------------------------------------
# NativeToolDispatcher
# ---------------------------------------------------------------------------

def test_dispatcher_register_and_specs():
    d = NativeToolDispatcher()
    spec = NativeToolSpec(name="read_file", description="Read.")
    d.register(spec, lambda call_id, inp: NativeToolResult(call_id=call_id, tool_name="read_file", output="ok"))
    assert len(d.specs()) == 1
    assert d.get_spec("read_file") is not None
    assert d.get_spec("unknown") is None


def test_dispatcher_dispatch_known_tool():
    d = NativeToolDispatcher()
    spec = NativeToolSpec(name="read_file", description="Read.")
    d.register(spec, lambda call_id, inp: NativeToolResult(call_id=call_id, tool_name="read_file", output="data"))
    call = NativeToolCall(tool_name="read_file", input={}, call_id="c1")
    result = d.dispatch(call)
    assert result.status == "success"
    assert result.output == "data"


def test_dispatcher_dispatch_unknown_tool():
    d = NativeToolDispatcher()
    call = NativeToolCall(tool_name="nonexistent", call_id="c1")
    result = d.dispatch(call)
    assert result.status == "error"
    assert "nonexistent" in result.error


def test_dispatcher_handler_exception_returns_error():
    d = NativeToolDispatcher()
    spec = NativeToolSpec(name="bad_tool", description="Breaks.")

    def bad_handler(call_id, inp):
        raise ValueError("oops")

    d.register(spec, bad_handler)
    call = NativeToolCall(tool_name="bad_tool", call_id="c1")
    result = d.dispatch(call)
    assert result.status == "error"
    assert "ValueError" in result.error


def test_dispatcher_specs_sorted_by_name():
    d = NativeToolDispatcher()
    for name in ("z_tool", "a_tool", "m_tool"):
        spec = NativeToolSpec(name=name, description=".")
        d.register(spec, lambda cid, inp: NativeToolResult(call_id=cid, tool_name=name))
    names = [s.name for s in d.specs()]
    assert names == sorted(names)


def test_dispatcher_system_prompt_section():
    d = NativeToolDispatcher()
    d.register(
        NativeToolSpec(name="read_file", description="Read a file."),
        lambda cid, inp: NativeToolResult(call_id=cid, tool_name="read_file"),
    )
    section = d.system_prompt_section()
    assert "## Available Tools" in section
    assert "read_file" in section


# ---------------------------------------------------------------------------
# AgentNativeToolCallResponse in schemas
# ---------------------------------------------------------------------------

def test_agent_native_tool_call_response_parses():
    raw = {"type": "native_tool_call", "tool_name": "read_file", "input": {"path": "foo.py"}}
    result = validate_provider_json(raw, step=1, method="choose_tool")
    assert isinstance(result, AgentNativeToolCallResponse)
    assert result.tool_name == "read_file"


def test_agent_native_tool_call_response_missing_tool_name_is_recoverable():
    from safecode.agent.schemas import RecoverableContractFailure
    raw = {"type": "native_tool_call"}
    result = validate_provider_json(raw, step=1, method="choose_tool")
    assert isinstance(result, RecoverableContractFailure)


# ---------------------------------------------------------------------------
# B4: TOKEN_CHAR_RATIO changed from 4 to 3.5, code ratio 3.2
# ---------------------------------------------------------------------------

def test_b4_token_ratio_is_3_5():
    assert TOKEN_CHAR_RATIO == 3.5


def test_b4_code_token_ratio_is_3_2():
    assert _CODE_TOKEN_CHAR_RATIO == 3.2


def test_b4_estimate_tokens_text_uses_3_5():
    # 350 bytes / 3.5 = 100 tokens
    assert estimate_tokens_from_bytes(350, content_type="text") == 100


def test_b4_estimate_tokens_code_uses_3_2():
    # 320 bytes / 3.2 = 100 tokens
    assert estimate_tokens_from_bytes(320, content_type="code") == 100


def test_b4_estimate_tokens_default_is_text():
    assert estimate_tokens_from_bytes(350) == estimate_tokens_from_bytes(350, content_type="text")


def test_b4_estimate_tokens_zero():
    assert estimate_tokens_from_bytes(0) == 0
    assert estimate_tokens_from_bytes(-1) == 0


# ---------------------------------------------------------------------------
# B5: file tree truncation is surfaced in _list_files return value
# ---------------------------------------------------------------------------

def test_b5_file_tree_truncation_flagged(tmp_path: Path):
    # Create more files than max_tree_files
    for i in range(5):
        (tmp_path / f"file_{i}.py").write_text(f"# file {i}")
    config = SafeCodeConfig(max_tree_files=3)
    collector = ContextCollector(tmp_path, config=config)
    files, truncated = collector._list_files()
    assert truncated is True
    assert len(files) == 3


def test_b5_no_truncation_flag_when_under_cap(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")
    config = SafeCodeConfig(max_tree_files=100)
    collector = ContextCollector(tmp_path, config=config)
    files, truncated = collector._list_files()
    assert truncated is False
    assert len(files) == 2


def test_b5_collect_adds_file_tree_meta_when_truncated(tmp_path: Path, monkeypatch):
    """collect() exposes file_tree_meta when truncation occurs."""
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text(f"x={i}")
    config = SafeCodeConfig(max_tree_files=2)
    collector = ContextCollector(tmp_path, config=config)
    # Stub repo_map_summary to avoid FileIndexer issue in tmp_path
    monkeypatch.setattr(collector, "_repo_map_summary", lambda: {})
    ctx = collector.collect()
    assert ctx.get("file_tree_meta", {}).get("truncated") is True


# ---------------------------------------------------------------------------
# B17: aggregate context byte cap stops new sources
# ---------------------------------------------------------------------------

def test_b17_budget_cap_stops_sources_at_zero():
    budget = ContextBudget(max_bytes=10)
    packer = ContextBudgetPacker(budget)
    context = {
        "first": "hello",   # 5 bytes
        "second": "world!",  # 6 bytes - would overflow
    }
    packed, report = packer.pack(context)
    assert len(packed["first"]) <= 10
    assert len(packed["second"]) <= 5  # truncated because remaining is now ≤5 chars
    # At least one truncation note should exist
    assert any("second" in note or "first" in note for note in report.truncation_notes) or report.bytes_used <= 10


def test_b17_skipped_source_gets_empty_string():
    budget = ContextBudget(max_bytes=0)
    packer = ContextBudgetPacker(budget)
    context = {"key": "some long content that wont fit"}
    packed, report = packer.pack(context)
    assert packed["key"] == ""
    assert any("budget exceeded" in note for note in report.truncation_notes)


def test_b17_non_string_keys_pass_through():
    budget = ContextBudget(max_bytes=0)
    packer = ContextBudgetPacker(budget)
    context = {"metadata": {"foo": "bar"}, "key": "text"}
    packed, report = packer.pack(context)
    # Non-string/list values always pass through
    assert packed["metadata"] == {"foo": "bar"}
