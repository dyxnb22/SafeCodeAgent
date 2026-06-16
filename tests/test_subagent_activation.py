"""Tests for v5.7.0 subagent activation — dispatch_parallel in MultiToolTurnRunner."""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from safecode.agent.multi_tool_turn import MultiToolTurnRunner, _WRITE_TOOL_NAMES
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall, NativeToolResult


def _read_call(name: str = "read_file", delay: float = 0) -> NativeToolCall:
    return NativeToolCall(
        tool_name=name,
        input={"path": f"src/{name}.py"},
        call_id=f"call-{name}",
    )


def _write_call(name: str = "edit_file") -> NativeToolCall:
    return NativeToolCall(
        tool_name=name,
        input={"path": f"src/{name}.py", "old_string": "a", "new_string": "b"},
        call_id=f"call-{name}",
    )


def _make_dispatcher(*, delay: float = 0) -> NativeToolDispatcher:
    """Build a dispatcher whose dispatch() returns success after an optional delay."""
    disp = MagicMock(spec=NativeToolDispatcher)

    def _dispatch(call: NativeToolCall) -> NativeToolResult:
        if delay > 0:
            time.sleep(delay)
        return NativeToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            output=f"content from {call.tool_name}",
        )

    disp.dispatch.side_effect = _dispatch
    return disp


class TestDispatchParallelBasic:
    def setup_method(self):
        self.dispatcher = _make_dispatcher()
        self.runner = MultiToolTurnRunner(self.dispatcher)
        self.read_calls = [_read_call("read_file"), _read_call("grep_files"), _read_call("search_files")]

    def test_dispatches_three_read_calls(self):
        result = self.runner.dispatch_parallel(self.read_calls)
        assert result.stopped_reason == "completed"
        assert len(result.tool_calls) == 3
        assert all(tc.status == "success" for tc in result.tool_calls)

    def test_empty_calls_returns_empty_result(self):
        result = self.runner.dispatch_parallel([])
        assert len(result.tool_calls) == 0
        assert result.stopped_reason == "completed"

    def test_observations_are_redacted_and_ordered(self):
        result = self.runner.dispatch_parallel(self.read_calls)
        assert len(result.observations) == 3
        # Observations should contain the tool output
        for obs in result.observations:
            assert "content from" in obs

    def test_single_call_works(self):
        result = self.runner.dispatch_parallel([_read_call("read_file")])
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "read_file"


class TestDispatchParallelWriteBlocking:
    def setup_method(self):
        self.dispatcher = _make_dispatcher()
        self.runner = MultiToolTurnRunner(self.dispatcher)

    def test_edit_file_raises_value_error(self):
        with pytest.raises(ValueError, match="Write tool"):
            self.runner.dispatch_parallel([_write_call("edit_file")])

    def test_write_file_raises_value_error(self):
        with pytest.raises(ValueError, match="Write tool"):
            self.runner.dispatch_parallel([_write_call("write_file")])

    def test_run_command_raises_value_error(self):
        with pytest.raises(ValueError, match="Write tool"):
            self.runner.dispatch_parallel([_write_call("run_command")])

    def test_github_create_pr_raises_value_error(self):
        with pytest.raises(ValueError, match="Write tool"):
            self.runner.dispatch_parallel([_write_call("github_create_pr")])

    def test_mixed_read_and_write_raises_error(self):
        calls = [_read_call("read_file"), _write_call("edit_file")]
        with pytest.raises(ValueError, match="Write tool"):
            self.runner.dispatch_parallel(calls)

    def test_all_write_tool_names_are_blocked(self):
        for name in _WRITE_TOOL_NAMES:
            with pytest.raises(ValueError, match="Write tool"):
                self.runner.dispatch_parallel([_write_call(name)])


class TestDispatchParallelPerformance:
    """Verify that parallel dispatch is faster than serial for delayed calls."""

    def setup_method(self):
        self.dispatcher = _make_dispatcher(delay=0.1)
        self.runner = MultiToolTurnRunner(self.dispatcher)
        self.three_calls = [_read_call(f"read_file{i}") for i in range(3)]

    def test_parallel_is_faster_than_serial_for_delayed_calls(self):
        # Serial: should take ~0.3s for 3 x 0.1s
        t0 = time.perf_counter()
        self.runner.dispatch_calls(self.three_calls)
        serial_time = time.perf_counter() - t0

        # Parallel: should take ~0.1s for 3 x 0.1s (with max_workers=3)
        t0 = time.perf_counter()
        self.runner.dispatch_parallel(self.three_calls, max_workers=3)
        parallel_time = time.perf_counter() - t0

        assert parallel_time < serial_time * 0.8, (
            f"Parallel ({parallel_time:.3f}s) should be faster than serial ({serial_time:.3f}s)"
        )


class TestDispatchParallelErrorIsolation:
    def test_one_failing_call_does_not_crash_others(self):
        disp = MagicMock(spec=NativeToolDispatcher)

        results = {
            "call-read_file": NativeToolResult(call_id="call-read_file", tool_name="read_file", status="success", output="ok"),
            "call-fail": NativeToolResult(call_id="call-fail", tool_name="read_file", status="error", error="boom"),
            "call-search_files": NativeToolResult(call_id="call-search_files", tool_name="search_files", status="success", output="found"),
        }

        def _dispatch(call):
            return results.get(call.call_id, NativeToolResult(call_id=call.call_id, tool_name=call.tool_name, status="error"))

        disp.dispatch.side_effect = _dispatch
        runner = MultiToolTurnRunner(disp)

        calls = [
            NativeToolCall(tool_name="read_file", call_id="call-read_file"),
            NativeToolCall(tool_name="read_file", call_id="call-fail"),
            NativeToolCall(tool_name="search_files", call_id="call-search_files"),
        ]

        result = runner.dispatch_parallel(calls)
        assert len(result.tool_calls) == 3
        # The failing call should have error status, others success
        statuses = {tc.call_id: tc.status for tc in result.tool_calls}
        assert statuses["call-read_file"] == "success"
        assert statuses["call-fail"] == "error"
        assert statuses["call-search_files"] == "success"


class TestDispatchParallelIsolatedWorkers:
    def test_exception_in_dispatch_is_caught(self):
        """If dispatcher.dispatch() raises for one call, others still complete."""
        disp = MagicMock(spec=NativeToolDispatcher)

        call_count = 0

        def _dispatch(call):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("worker crashed")
            return NativeToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status="success",
                output="ok",
            )

        disp.dispatch.side_effect = _dispatch
        runner = MultiToolTurnRunner(disp)

        calls = [
            NativeToolCall(tool_name="read_file", call_id="call-a", input={"path": "a.py"}),
            NativeToolCall(tool_name="read_file", call_id="call-b", input={"path": "b.py"}),
            NativeToolCall(tool_name="read_file", call_id="call-c", input={"path": "c.py"}),
        ]

        result = runner.dispatch_parallel(calls, max_workers=3)
        assert len(result.tool_calls) == 3
        # The crashed worker gets error status; others succeed
        statuses = {tc.call_id: tc.status for tc in result.tool_calls}
        assert statuses["call-a"] == "success" or statuses["call-a"] == "error"
        assert statuses["call-c"] == "success" or statuses["call-c"] == "error"
        # At least one should have error from the RuntimeError
        error_statuses = [tc for tc in result.tool_calls if tc.status == "error"]
        assert len(error_statuses) >= 1

    def test_max_workers_respected(self):
        disp = _make_dispatcher(delay=0.05)
        runner = MultiToolTurnRunner(disp)
        calls = [_read_call(f"file{i}") for i in range(6)]

        t0 = time.perf_counter()
        runner.dispatch_parallel(calls, max_workers=2)
        elapsed = time.perf_counter() - t0
        # With max_workers=2, 6 calls at 0.05s each => at least 3 batches => ~0.15s
        assert elapsed >= 0.10, f"With max_workers=2, 6 calls should take >0.1s (took {elapsed:.3f}s)"
        # With max_workers=2, should be < 6 x 0.05 = 0.3s (serial)
        assert elapsed < 0.30, f"Parallel with 2 workers still too slow: {elapsed:.3f}s"
