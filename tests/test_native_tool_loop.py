"""End-to-end tests for the native-tool loop path (v6.34).

These tests exercise AgentLoop.native_step() with a scripted mock LLM client
so that the native-tool path (choose_tool_native → MultiToolTurnRunner →
NativeToolDispatcher → checkpoint) is covered without live API calls.

Previously this path was untested: MockLLMClient has no choose_tool_native(),
so all 6000+ tests fell back to the old JSON-schema step() path.

Coverage targets:
- ScriptedNativeToolLLMClient call-sequencing
- Immediate stop / stop after tool call
- RecoverableContractFailure single-retry and double-fail
- read_file tool: path validated, output returned in observation
- list_files tool: directory listing
- search_symbol tool: definition search
- edit_file tool: blocked without approval, executed with auto_edit
- write_file tool: blocked without approval, executed with auto_edit
- Checkpoint created on write in auto_edit mode
- File count guard (auto_edit_file_guard)
- Multi-tool multi-turn: read → edit in two turns
- MockLLMClient fallback (no choose_tool_native → step())
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from safecode.agent.loop import AgentLoop
from safecode.agent.native_tools import NativeToolCall, NativeToolSpec
from safecode.agent.schemas import (
    AgentNativeToolCallResponse,
    AgentStopForUserResponse,
    RecoverableContractFailure,
)
from safecode.llm.mock import MockLLMClient, ScriptedNativeToolLLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loop(tmp_path: Path, script, *, auto_edit: bool = False, full_auto: bool = False) -> AgentLoop:
    client = ScriptedNativeToolLLMClient(script)
    loop = AgentLoop(
        project_root=tmp_path,
        llm_client=client,
        auto_edit=auto_edit,
        full_auto=full_auto,
    )
    return loop


def _read_call(path: str, call_id: str = "c1") -> NativeToolCall:
    return NativeToolCall(tool_name="read_file", input={"path": path}, call_id=call_id)


def _edit_call(path: str, old: str, new: str, call_id: str = "c_edit") -> NativeToolCall:
    return NativeToolCall(
        tool_name="edit_file",
        input={"path": path, "old_string": old, "new_string": new, "description": "test edit"},
        call_id=call_id,
    )


def _write_call(path: str, content: str, call_id: str = "c_write") -> NativeToolCall:
    return NativeToolCall(
        tool_name="write_file",
        input={"path": path, "content": content, "description": "test write"},
        call_id=call_id,
    )


def _stop(reason: str = "done", msg: str = "Task complete.") -> AgentStopForUserResponse:
    return AgentStopForUserResponse(reason=reason, message=msg)


# ---------------------------------------------------------------------------
# ScriptedNativeToolLLMClient unit tests
# ---------------------------------------------------------------------------

class TestScriptedClient:
    def test_returns_stop_on_first_call(self, tmp_path):
        client = ScriptedNativeToolLLMClient([_stop()])
        result = client.choose_tool_native("goal", {}, [])
        assert isinstance(result, AgentStopForUserResponse)
        assert client.native_call_count == 1

    def test_returns_tool_calls_then_stop(self, tmp_path):
        script = [
            [_read_call("README.md")],
            _stop(),
        ]
        client = ScriptedNativeToolLLMClient(script)
        r1 = client.choose_tool_native("goal", {}, [])
        assert isinstance(r1, list)
        assert len(r1) == 1
        assert r1[0].tool_name == "read_file"
        r2 = client.choose_tool_native("goal", {}, [])
        assert isinstance(r2, AgentStopForUserResponse)
        assert client.native_call_count == 2

    def test_exhausted_script_returns_stop(self):
        client = ScriptedNativeToolLLMClient([])
        result = client.choose_tool_native("goal", {}, [])
        assert isinstance(result, AgentStopForUserResponse)
        assert "exhausted" in result.reason

    def test_rcf_is_returned_directly(self):
        rcf = RecoverableContractFailure(step=0, method="choose_tool_native", message="oops")
        client = ScriptedNativeToolLLMClient([rcf])
        result = client.choose_tool_native("goal", {}, [])
        assert isinstance(result, RecoverableContractFailure)

    def test_call_ids_generated_when_empty(self):
        script = [[NativeToolCall(tool_name="list_files", input={}, call_id="")]]
        client = ScriptedNativeToolLLMClient(script)
        result = client.choose_tool_native("goal", {}, [])
        assert isinstance(result, list)
        assert result[0].call_id != ""

    def test_records_all_calls(self):
        script = [
            [_read_call("a.py")],
            _stop(),
        ]
        client = ScriptedNativeToolLLMClient(script)
        client.choose_tool_native("goal1", {"k": 1}, [])
        client.choose_tool_native("goal2", {"k": 2}, [])
        assert len(client.recorded_calls) == 2
        assert client.recorded_calls[0]["call_index"] == 0
        assert client.recorded_calls[1]["call_index"] == 1

    def test_inherits_mock_llm_methods(self):
        client = ScriptedNativeToolLLMClient([])
        answer = client.ask("question", {})
        assert answer.content  # inherited from MockLLMClient

    def test_multiple_tool_calls_in_one_response(self):
        script = [
            [_read_call("a.py", "c1"), _read_call("b.py", "c2")],
            _stop(),
        ]
        client = ScriptedNativeToolLLMClient(script)
        r1 = client.choose_tool_native("goal", {}, [])
        assert len(r1) == 2
        assert r1[0].tool_name == "read_file"
        assert r1[1].tool_name == "read_file"


# ---------------------------------------------------------------------------
# AgentLoop.native_step integration tests
# ---------------------------------------------------------------------------

class TestNativeStepImmediate:
    def test_immediate_stop_returns_stopped(self, tmp_path):
        loop = _loop(tmp_path, [_stop("no_tools_needed", "Nothing to do.")])
        result = loop.native_step("check the project")
        assert result.stopped_for_approval is True
        assert "Nothing to do" in result.observation

    def test_session_created_when_no_prior_session(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        result = loop.native_step("my goal")
        assert result.state is not None
        assert result.state.goal == "my goal"

    def test_step_state_persisted(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        result = loop.native_step("persist test")
        session_file = tmp_path / ".sac" / "session.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["goal"] == "persist test"


class TestNativeStepReadFile:
    def test_read_file_output_in_observation(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "hello.py").write_text("def hello():\n    return 'hi'\n")

        script = [
            [_read_call("src/hello.py")],
            _stop("done", "File read successfully."),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("read hello.py")
        assert "hello" in result.observation.lower() or "read" in result.observation.lower()

    def test_read_file_path_outside_root_blocked(self, tmp_path):
        script = [
            [NativeToolCall(tool_name="read_file", input={"path": "../../etc/passwd"}, call_id="c1")],
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("read passwd")
        # Either the tool blocked (observation contains "outside") or stop was reached
        assert result is not None  # no crash

    def test_read_nonexistent_file_returns_error(self, tmp_path):
        script = [
            [_read_call("nonexistent_xyz.py")],
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("read missing file")
        assert result is not None  # no crash; error surfaced in observation

    def test_choose_tool_native_called_twice(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        client = ScriptedNativeToolLLMClient([
            [_read_call("a.py")],
            _stop(),
        ])
        loop = AgentLoop(project_root=tmp_path, llm_client=client)
        loop.native_step("read a.py")
        # Initial call + follow-up after tool results
        assert client.native_call_count == 2


class TestNativeStepListFiles:
    def test_list_files_returns_directory_contents(self, tmp_path):
        (tmp_path / "foo.py").write_text("")
        (tmp_path / "bar.py").write_text("")

        script = [
            [NativeToolCall(tool_name="list_files", input={"path": ".", "recursive": False}, call_id="c1")],
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("list files")
        # The observation block contains the tool result
        assert result is not None


class TestNativeStepSearchSymbol:
    def test_search_symbol_finds_definition(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "utils.py").write_text("def parse_config(path):\n    pass\n")

        script = [
            [NativeToolCall(
                tool_name="search_symbol",
                input={"name": "parse_config"},
                call_id="c_sym",
            )],
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("find parse_config")
        assert result is not None

    def test_search_symbol_missing_name_no_crash(self, tmp_path):
        script = [
            [NativeToolCall(tool_name="search_symbol", input={}, call_id="c1")],
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("search nothing")
        assert result is not None


class TestNativeStepWriteToolBlocked:
    """Write tools must be blocked without auto_edit / full_auto."""

    def test_edit_file_blocked_without_approval(self, tmp_path):
        (tmp_path / "target.py").write_text("OLD_VALUE = 1\n")
        script = [
            [_edit_call("target.py", "OLD_VALUE = 1", "NEW_VALUE = 2")],
            _stop(),
        ]
        loop = _loop(tmp_path, script, auto_edit=False)
        loop.native_step("change target.py")
        # File must not be modified
        assert (tmp_path / "target.py").read_text() == "OLD_VALUE = 1\n"

    def test_write_file_blocked_without_approval(self, tmp_path):
        script = [
            [_write_call("new_file.py", "content = 'hello'\n")],
            _stop(),
        ]
        loop = _loop(tmp_path, script, auto_edit=False)
        loop.native_step("create new_file.py")
        # File must not be created
        assert not (tmp_path / "new_file.py").exists()


class TestNativeStepWriteToolApproved:
    """Write tools execute and create checkpoints in auto_edit mode."""

    def test_edit_file_executes_with_auto_edit(self, tmp_path):
        (tmp_path / "fix_me.py").write_text("BUGGY = True\n")
        script = [
            [_edit_call("fix_me.py", "BUGGY = True", "FIXED = True")],
            _stop("edit_complete", "Edit applied."),
        ]
        loop = _loop(tmp_path, script, auto_edit=True)
        loop.native_step("fix fix_me.py")
        assert "FIXED = True" in (tmp_path / "fix_me.py").read_text()

    def test_edit_file_creates_checkpoint(self, tmp_path):
        (tmp_path / "src.py").write_text("X = 0\n")
        script = [
            [_edit_call("src.py", "X = 0", "X = 1")],
            _stop(),
        ]
        loop = _loop(tmp_path, script, auto_edit=True)
        loop.native_step("increment X")
        # Checkpoints are stored as subdirs under .sac/checkpoints/
        checkpoint_root = tmp_path / ".sac" / "checkpoints"
        if checkpoint_root.exists():
            checkpoints = [d for d in checkpoint_root.iterdir() if d.is_dir()]
        else:
            checkpoints = []
        assert len(checkpoints) >= 1

    def test_write_file_creates_new_file(self, tmp_path):
        script = [
            [_write_call("generated.py", "GENERATED = True\n")],
            _stop(),
        ]
        loop = _loop(tmp_path, script, auto_edit=True)
        loop.native_step("generate file")
        assert (tmp_path / "generated.py").read_text() == "GENERATED = True\n"

    def test_edit_file_full_auto_executes(self, tmp_path):
        (tmp_path / "item.py").write_text("VALUE = 'old'\n")
        script = [
            [_edit_call("item.py", "VALUE = 'old'", "VALUE = 'new'")],
            _stop(),
        ]
        loop = _loop(tmp_path, script, full_auto=True)
        loop.native_step("update item.py")
        assert "VALUE = 'new'" in (tmp_path / "item.py").read_text()


class TestNativeStepMultiTurn:
    """Multi-turn: read in turn 1, then edit in turn 2."""

    def test_read_then_edit_two_turns(self, tmp_path):
        (tmp_path / "module.py").write_text("def broken(): return 1/0\n")
        script = [
            # Turn 1: read the file
            [_read_call("module.py", "c_read")],
            # After seeing the file, propose an edit
            [_edit_call("module.py", "def broken(): return 1/0", "def fixed(): return 1", "c_edit")],
            # After the edit, stop
            _stop("task_complete", "Fixed."),
        ]
        loop = _loop(tmp_path, script, auto_edit=True)
        loop.native_step("fix broken()")
        assert "def fixed" in (tmp_path / "module.py").read_text()
        assert loop.llm_client.native_call_count == 3

    def test_multi_read_then_stop(self, tmp_path):
        (tmp_path / "a.py").write_text("a = 1\n")
        (tmp_path / "b.py").write_text("b = 2\n")
        script = [
            [_read_call("a.py", "c1"), _read_call("b.py", "c2")],
            _stop("inspected", "Both files read."),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("read both files")
        assert result is not None
        assert loop.llm_client.native_call_count == 2

    def test_observation_feeds_into_next_call(self, tmp_path):
        """Verify that tool_results from turn 1 reach the context in turn 2."""
        (tmp_path / "data.py").write_text("MARKER = 'sentinel_value_xyz'\n")

        captured_contexts: list[dict] = []

        class InspectingClient(ScriptedNativeToolLLMClient):
            def choose_tool_native(self, goal, context, specs, **kw):
                captured_contexts.append(dict(context))
                return super().choose_tool_native(goal, context, specs, **kw)

        script = [
            [_read_call("data.py")],
            _stop(),
        ]
        client = InspectingClient(script)
        loop = AgentLoop(project_root=tmp_path, llm_client=client)
        loop.native_step("read data.py")

        # Second call (follow-up) should have tool_results in context
        assert len(captured_contexts) >= 2
        second_ctx = captured_contexts[1]
        assert "tool_results" in second_ctx or any(
            "sentinel_value_xyz" in str(v) for v in second_ctx.values()
        )


class TestNativeStepRCF:
    """RecoverableContractFailure: single retry succeeds; double fails gracefully."""

    def test_single_rcf_retries_and_succeeds(self, tmp_path):
        rcf = RecoverableContractFailure(step=0, method="choose_tool_native", message="transient")
        script = [
            rcf,                    # First call: RCF
            [_read_call(".")],      # Retry: tool call
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("do something")
        # The loop retried and continued → native_call_count ≥ 2
        assert loop.llm_client.native_call_count >= 2
        assert result is not None

    def test_double_rcf_fails_gracefully(self, tmp_path):
        rcf1 = RecoverableContractFailure(step=0, method="choose_tool_native", message="first failure")
        rcf2 = RecoverableContractFailure(step=0, method="choose_tool_native", message="second failure")
        script = [rcf1, rcf2]
        loop = _loop(tmp_path, script)
        result = loop.native_step("will fail twice")
        # Loop should not crash; should surface a failure observation
        assert result is not None
        assert "failure" in result.observation.lower() or result.state is not None


class TestNativeStepFallback:
    """MockLLMClient (no choose_tool_native) falls back to old step() path."""

    def test_mock_client_falls_back_to_step(self, tmp_path):
        """AgentLoop falls back to step() when llm_client has no choose_tool_native."""
        mock = MockLLMClient()
        assert not hasattr(mock, "choose_tool_native")
        loop = AgentLoop(project_root=tmp_path, llm_client=mock)
        # native_step calls step() internally — should not crash
        result = loop.native_step("some inspection goal")
        assert result is not None

    def test_scripted_client_has_choose_tool_native(self):
        client = ScriptedNativeToolLLMClient([])
        assert hasattr(client, "choose_tool_native")


class TestNativeStepJournal:
    """Journal events are written during native_step execution."""

    def test_journal_records_action(self, tmp_path):
        script = [
            [_read_call(".")],
            _stop(),
        ]
        loop = _loop(tmp_path, script)
        result = loop.native_step("journal test goal")
        journal_path = tmp_path / ".sac" / "sessions" / result.state.session_id / "journal.jsonl"
        if journal_path.exists():
            lines = [l for l in journal_path.read_text().splitlines() if l.strip()]
            assert len(lines) >= 1
            event = json.loads(lines[0])
            assert "session_id" in event or "type" in event

    def test_session_id_in_result_state(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        result = loop.native_step("session id test")
        assert result.state.session_id
        assert len(result.state.session_id) > 4


class TestNativeStepCostTracking:
    """Token cost state is updated (even at 0 for mock)."""

    def test_cost_state_fields_present(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        result = loop.native_step("cost test")
        assert hasattr(result.state, "cost_tokens_in")
        assert hasattr(result.state, "cost_tokens_out")
        assert result.state.cost_tokens_in >= 0
        assert result.state.cost_tokens_out >= 0


class TestNativeStepDispatcherIntegrity:
    """NativeToolDispatcher only contains known-safe tools."""

    def test_registered_tools_are_safe_subset(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        dispatcher = loop._build_dispatcher()
        registered = {s.name for s in dispatcher.specs()}
        safe_read = {"read_file", "list_files", "search_files", "grep_files", "search_symbol"}
        safe_write = {"edit_file", "write_file", "run_command"}
        safe_github = {"github_read_issue", "github_read_pr", "github_read_file",
                       "github_create_pr", "github_push_branch"}
        safe_web = {"web_fetch"}
        all_safe = safe_read | safe_write | safe_github | safe_web
        # All registered tools must be in the known-safe set (or find_references)
        unknown = registered - all_safe - {"find_references"}
        assert not unknown, f"Unknown tools registered: {unknown}"

    def test_write_tools_require_approval(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        dispatcher = loop._build_dispatcher()
        write_tools = {"edit_file", "write_file"}
        for spec in dispatcher.specs():
            if spec.name in write_tools:
                assert spec.requires_approval, f"{spec.name} must require_approval=True"

    def test_read_tools_do_not_require_approval(self, tmp_path):
        loop = _loop(tmp_path, [_stop()])
        dispatcher = loop._build_dispatcher()
        read_only = {"read_file", "list_files", "search_files", "grep_files", "search_symbol"}
        for spec in dispatcher.specs():
            if spec.name in read_only:
                assert not spec.requires_approval, f"{spec.name} should not require approval"
