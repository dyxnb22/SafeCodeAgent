"""Tests for MultiToolTurnRunner and B9 stuck-loop fix (v4.22.0, EXPERIMENTAL)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.agent.multi_tool_turn import MultiToolTurnRunner, _MAX_TURN_TOOLS, _CAP_HIT_REASON
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall, NativeToolResult, NativeToolSpec


def _echo_handler(call_id: str, inp: dict) -> NativeToolResult:
    return NativeToolResult(call_id=call_id, tool_name="echo", output=inp.get("msg", ""))


def _error_handler(call_id: str, inp: dict) -> NativeToolResult:
    return NativeToolResult(call_id=call_id, tool_name="fail_tool", status="error", error="boom")


def _make_dispatcher(tools=None) -> NativeToolDispatcher:
    d = NativeToolDispatcher()
    d.register(NativeToolSpec(name="echo", description="echo"), _echo_handler)
    d.register(NativeToolSpec(name="fail_tool", description="fails"), _error_handler)
    return d


def _make_call(tool_name="echo", msg="hello", call_id="c1") -> NativeToolCall:
    return NativeToolCall(tool_name=tool_name, input={"msg": msg}, call_id=call_id)


# ---------------------------------------------------------------------------
# dispatch_calls
# ---------------------------------------------------------------------------

def test_dispatch_single_call():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [_make_call(msg="world")]
    result = runner.dispatch_calls(calls)
    assert len(result.tool_calls) == 1
    assert "world" in result.observations[0]
    assert result.stopped_reason == "completed"
    assert result.cap_hit is False


def test_dispatch_multiple_calls():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [_make_call(msg=f"m{i}", call_id=f"c{i}") for i in range(3)]
    result = runner.dispatch_calls(calls)
    assert len(result.tool_calls) == 3
    assert len(result.observations) == 3


def test_dispatch_cap_hit():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d, max_turn_tools=2)
    calls = [_make_call(msg=f"m{i}", call_id=f"c{i}") for i in range(5)]
    result = runner.dispatch_calls(calls)
    assert len(result.tool_calls) == 2
    assert result.cap_hit is True
    assert result.stopped_reason == _CAP_HIT_REASON


def test_dispatch_error_tool_recorded():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [NativeToolCall(tool_name="fail_tool", input={}, call_id="c1")]
    result = runner.dispatch_calls(calls)
    assert result.tool_calls[0].status == "error"
    assert "error" in result.observations[0].lower()


def test_dispatch_unknown_tool_returns_error():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [NativeToolCall(tool_name="unknown", input={}, call_id="c1")]
    result = runner.dispatch_calls(calls)
    assert result.tool_calls[0].status == "error"


def test_context_block_joins_observations():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [_make_call(msg="a", call_id="c1"), _make_call(msg="b", call_id="c2")]
    result = runner.dispatch_calls(calls)
    block = result.context_block()
    assert "a" in block
    assert "b" in block


def test_input_summary_is_redacted():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [_make_call(msg="API_KEY=supersecret123")]
    result = runner.dispatch_calls(calls)
    assert "supersecret123" not in result.tool_calls[0].input_summary


def test_output_snippet_is_redacted():
    d = NativeToolDispatcher()

    def secret_handler(call_id, inp):
        return NativeToolResult(call_id=call_id, tool_name="leak", output="API_KEY=secret456")

    d.register(NativeToolSpec(name="leak", description="leaks"), secret_handler)
    runner = MultiToolTurnRunner(d)
    calls = [NativeToolCall(tool_name="leak", input={}, call_id="c1")]
    result = runner.dispatch_calls(calls)
    assert "secret456" not in result.tool_calls[0].output_snippet


# ---------------------------------------------------------------------------
# run_turn — no llm_next_fn
# ---------------------------------------------------------------------------

def test_run_turn_no_llm_fn_dispatches_once():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    calls = [_make_call(msg="once")]
    result = runner.run_turn(calls)
    assert len(result.tool_calls) == 1
    assert result.stopped_reason == "completed"


def test_run_turn_cap_enforced():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d, max_turn_tools=3)
    calls = [_make_call(msg=f"m{i}", call_id=f"c{i}") for i in range(10)]
    result = runner.run_turn(calls)
    assert len(result.tool_calls) == 3
    assert result.cap_hit is True


# ---------------------------------------------------------------------------
# run_turn — with llm_next_fn (simulating model-driven multi-turn)
# ---------------------------------------------------------------------------

def test_run_turn_with_llm_fn_stops_when_none_returned():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d)
    call_count = {"n": 0}

    def llm_next(obs_text, ctx):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return [_make_call(msg="next", call_id=f"next{call_count['n']}")]
        return None  # done

    calls = [_make_call(msg="first")]
    result = runner.run_turn(calls, llm_next_fn=llm_next)
    assert len(result.tool_calls) == 2  # initial + one from llm_next
    assert result.stopped_reason == "completed"


def test_run_turn_with_llm_fn_cap_stops_loop():
    d = _make_dispatcher()
    runner = MultiToolTurnRunner(d, max_turn_tools=3)

    def llm_next(obs_text, ctx):
        return [_make_call(msg="loop", call_id="loop")]

    calls = [_make_call(msg="start")]
    result = runner.run_turn(calls, llm_next_fn=llm_next)
    assert len(result.tool_calls) <= 3
    assert result.cap_hit is True


# ---------------------------------------------------------------------------
# identity_sequence (for stuck-loop detection)
# ---------------------------------------------------------------------------

def test_identity_sequence_consistent():
    runner = MultiToolTurnRunner(_make_dispatcher())
    calls = [NativeToolCall(tool_name="echo", input={"a": 1}, call_id="c1")]
    seq1 = runner.identity_sequence(calls)
    seq2 = runner.identity_sequence(calls)
    assert seq1 == seq2


def test_identity_sequence_differs_on_tool_name():
    runner = MultiToolTurnRunner(_make_dispatcher())
    calls_a = [NativeToolCall(tool_name="echo", input={}, call_id="c1")]
    calls_b = [NativeToolCall(tool_name="fail_tool", input={}, call_id="c1")]
    assert runner.identity_sequence(calls_a) != runner.identity_sequence(calls_b)


# ---------------------------------------------------------------------------
# B9: stuck-loop guard fires outside task scope
# ---------------------------------------------------------------------------

def test_b9_stuck_loop_emits_warning_without_current_task(tmp_path: Path):
    """B9: outside task scope, repeated intents emit RuntimeWarning (not abort)."""
    import warnings
    import inspect
    from safecode.agent.loop import AgentLoop

    src = inspect.getsource(AgentLoop._abort_if_stuck_tool_intent)
    # B9 implementation: tracks has_current_task and emits warning outside task scope
    assert "has_current_task" in src
    assert "RuntimeWarning" in src


def test_b9_stuck_loop_aborts_with_current_task(tmp_path: Path):
    """B9: inside task scope, repeated intents still cause abort."""
    import inspect
    from safecode.agent.loop import AgentLoop
    src = inspect.getsource(AgentLoop._abort_if_stuck_tool_intent)
    # Guard still aborts when has_current_task is True
    assert "loop_stuck" in src
    assert "aborted" in src


def test_b9_loop_stuck_guard_present():
    """Sanity: stuck-loop guard still exists (not accidentally removed)."""
    from safecode.agent.loop import AgentLoop
    import inspect
    src = inspect.getsource(AgentLoop._abort_if_stuck_tool_intent)
    assert "_last_tool_intent_count" in src
    assert "loop_stuck" in src
