"""Tests for v2.2.2: MCP read-only tool loop integration."""

from __future__ import annotations

import pytest

from safecode.agent.tools import ToolIntentRouter
from safecode.mcp.loop_executor import MCPLoopResult, MCPReadToolExecutor, _parse_tool_name
from safecode.mcp.runner import MCPRunResult
from safecode.state.journal import AgentJournalStore


# ── Router: read-only MCP classification ─────────────────────────────────────


class TestMCPRouter:
    def test_readonly_tool_name_routes_without_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.search"})
        assert routed.route == "mcp.call_readonly"
        assert routed.executable_now is True
        assert routed.intent.requires_approval is False

    def test_readonly_tool_name_reason_is_safe_to_route(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "myserver.list"})
        assert routed.reason == "safe_to_route"

    def test_write_tool_name_requires_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.create"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True

    def test_unknown_tool_name_requires_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.xyzzy"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True

    def test_delete_tool_name_requires_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "repo.delete"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False

    def test_get_tool_name_routes_without_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "db.get"})
        assert routed.route == "mcp.call_readonly"
        assert routed.executable_now is True

    def test_fetch_tool_name_routes_without_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "api.fetch"})
        assert routed.route == "mcp.call_readonly"
        assert routed.executable_now is True

    def test_intent_tool_name_is_preserved(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.search"})
        assert routed.intent.tool_name == "notion.search"

    def test_missing_tool_name_still_fails_closed(self):
        with pytest.raises(ValueError, match="requires tool_name"):
            ToolIntentRouter().route({"type": "mcp"})


# ── _parse_tool_name helper ───────────────────────────────────────────────────


class TestParseToolName:
    def test_valid_server_dot_tool(self):
        server, tool = _parse_tool_name("notion.search")
        assert server == "notion"
        assert tool == "search"

    def test_underscore_tool_name(self):
        server, tool = _parse_tool_name("myserver.list_files")
        assert server == "myserver"
        assert tool == "list_files"

    def test_no_dot_returns_empty_server(self):
        server, tool = _parse_tool_name("nodot")
        assert server == ""
        assert tool == "nodot"

    def test_empty_string_returns_empty_server(self):
        server, tool = _parse_tool_name("")
        assert server == ""

    def test_leading_dot_returns_empty_server(self):
        server, tool = _parse_tool_name(".search")
        assert server == ""

    def test_trailing_dot_returns_empty_server(self):
        server, tool = _parse_tool_name("notion.")
        assert server == ""

    def test_multiple_dots_uses_first(self):
        server, tool = _parse_tool_name("a.b.c")
        assert server == "a"
        assert tool == "b.c"


# ── MCPReadToolExecutor ───────────────────────────────────────────────────────


class TestMCPReadToolExecutor:
    def test_valid_readonly_call_returns_observation(self, tmp_path, monkeypatch):
        fake_result = MCPRunResult(
            server="notion",
            tool="search",
            classification="read",
            output="Found 3 pages.",
            error="",
            exit_code=0,
            duration_ms=10,
            executed=True,
            blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeRunner(fake_result),
        )
        result = MCPReadToolExecutor(tmp_path).execute("notion.search", {})
        assert result.success is True
        assert result.blocked is False
        assert "Found 3 pages." in result.observation
        assert result.server == "notion"
        assert result.tool == "search"

    def test_invalid_tool_name_format_fails_closed(self, tmp_path):
        result = MCPReadToolExecutor(tmp_path).execute("nodot")
        assert result.blocked is True
        assert result.success is False
        assert "server.tool" in result.observation

    def test_write_tool_name_fails_closed(self, tmp_path, monkeypatch):
        # "notion.write" is write-classified — executor rejects it before calling runner
        called = []
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _RecordingRunner(called),
        )
        result = MCPReadToolExecutor(tmp_path).execute("notion.write", {})
        assert result.blocked is True
        assert result.success is False
        assert "not read-only" in result.observation
        assert not called

    def test_unknown_classification_fails_closed(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _RecordingRunner(called),
        )
        result = MCPReadToolExecutor(tmp_path).execute("notion.xyzzy", {})
        assert result.blocked is True
        assert not called

    def test_runner_exception_becomes_safe_observation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _ErrorRunner(RuntimeError("connection refused")),
        )
        result = MCPReadToolExecutor(tmp_path).execute("notion.search", {})
        assert result.success is False
        assert "connection refused" in result.observation

    def test_runner_blocked_result_is_safe(self, tmp_path, monkeypatch):
        fake_result = MCPRunResult(
            server="notion",
            tool="search",
            classification="read",
            output="",
            error="MCP server is not configured.",
            exit_code=126,
            duration_ms=0,
            executed=False,
            blocked=True,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeRunner(fake_result),
        )
        result = MCPReadToolExecutor(tmp_path).execute("notion.search", {})
        assert result.blocked is True
        assert result.success is False
        assert "MCP server is not configured." in result.observation

    def test_empty_output_returns_no_output_message(self, tmp_path, monkeypatch):
        fake_result = MCPRunResult(
            server="db",
            tool="get",
            classification="read",
            output="",
            error="",
            exit_code=0,
            duration_ms=5,
            executed=True,
            blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeRunner(fake_result),
        )
        result = MCPReadToolExecutor(tmp_path).execute("db.get", {})
        assert result.success is True
        assert "no output" in result.observation

    def test_input_json_none_treated_as_empty_dict(self, tmp_path, monkeypatch):
        fake_result = MCPRunResult(
            server="api",
            tool="fetch",
            classification="read",
            output="ok",
            error="",
            exit_code=0,
            duration_ms=5,
            executed=True,
            blocked=False,
        )
        runner_inputs = []
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _CapturingRunner(fake_result, runner_inputs),
        )
        MCPReadToolExecutor(tmp_path).execute("api.fetch", None)
        assert runner_inputs[0] == {}

    def test_result_is_frozen(self, tmp_path, monkeypatch):
        fake_result = MCPRunResult(
            server="notion", tool="search", classification="read",
            output="x", error="", exit_code=0, duration_ms=1,
            executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeRunner(fake_result),
        )
        result = MCPReadToolExecutor(tmp_path).execute("notion.search", {})
        with pytest.raises(Exception):
            result.success = True  # type: ignore[misc]


# ── Journal record_mcp_call ───────────────────────────────────────────────────


class TestJournalMCPCall:
    def test_record_mcp_call_creates_event(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        session_id = "abc12345"
        event = store.record_mcp_call(
            session_id, 1, "MCP call completed.", {"tool_name": "notion.search"}
        )
        assert event.type == "mcp_call"
        assert event.session_id == session_id
        assert event.step == 1

    def test_record_mcp_call_payload_has_mcp_call_key(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        event = store.record_mcp_call(
            "abc12345", 2, "result", {"tool_name": "notion.search", "success": True}
        )
        assert "mcp_call" in event.payload
        assert event.payload["mcp_call"]["tool_name"] == "notion.search"

    def test_record_mcp_call_is_persisted_and_readable(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        session_id = "abc12345"
        store.record_mcp_call(session_id, 0, "done", {"tool_name": "db.get"})
        events = store.read(session_id)
        assert any(e.type == "mcp_call" for e in events)


# ── Agent loop integration ────────────────────────────────────────────────────


class TestAgentLoopMCPReadonly:
    def test_loop_executes_mcp_readonly_step(self, tmp_path, monkeypatch):
        """Loop step with a read-only MCP intent executes the tool and captures observation."""
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_intent(monkeypatch, "notion.search", {})
        _patch_mcp_executor(monkeypatch, observation="Found 5 results.", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="search notion")

        assert "notion.search" in result.observation
        assert "Found 5 results." in result.observation
        assert result.stopped_for_approval is False

    def test_loop_mcp_step_increments_current_step(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_intent(monkeypatch, "notion.search", {})
        _patch_mcp_executor(monkeypatch, observation="ok", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="search notion")

        assert result.state.current_step == 1

    def test_loop_mcp_step_writes_mcp_call_journal_event(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_intent(monkeypatch, "notion.search", {})
        _patch_mcp_executor(monkeypatch, observation="result data", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="search notion")

        session_id = result.state.session_id
        journal = AgentJournalStore(tmp_path)
        events = journal.read(session_id)
        mcp_events = [e for e in events if e.type == "mcp_call"]
        assert mcp_events, "Expected at least one mcp_call journal event"
        assert mcp_events[0].payload["mcp_call"]["tool_name"] == "notion.search"

    def test_loop_mcp_blocked_does_not_crash(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_intent(monkeypatch, "notion.search", {})
        _patch_mcp_executor(
            monkeypatch,
            observation="MCP server is not configured.",
            success=False,
            blocked=True,
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="search notion")

        assert "MCP server is not configured." in result.observation
        assert result.stopped_for_approval is False

    def test_loop_mcp_blocked_records_last_error(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_intent(monkeypatch, "notion.search", {})
        _patch_mcp_executor(
            monkeypatch,
            observation="MCP server is not configured.",
            success=False,
            blocked=True,
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="search notion")

        assert result.state.last_error is not None
        assert "MCP server is not configured." in result.state.last_error

    def test_loop_write_mcp_intent_stops_for_approval(self, tmp_path, monkeypatch):
        """Write-classified MCP intents still require approval; executor not called."""
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_intent(monkeypatch, "notion.create", {})
        called = []
        monkeypatch.setattr(
            "safecode.agent.loop.MCPReadToolExecutor",
            lambda *a, **kw: _RecordingRunner(called),
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        assert result.stopped_for_approval is False  # routed but not stopped
        # route is mcp.propose — pending_action should reflect this
        assert result.state.pending_action is not None
        assert result.state.pending_action.get("route") == "mcp.propose"
        assert not called


# ── Helpers ───────────────────────────────────────────────────────────────────


class _FakeRunner:
    def __init__(self, result: MCPRunResult) -> None:
        self._result = result

    def call_readonly(self, server, tool, input_data=None, trace_id=None):
        return self._result


class _RecordingRunner:
    def __init__(self, log: list) -> None:
        self._log = log

    def call_readonly(self, server, tool, input_data=None, trace_id=None):
        self._log.append((server, tool))
        raise RuntimeError("should not be called")


class _ErrorRunner:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def call_readonly(self, server, tool, input_data=None, trace_id=None):
        raise self._exc


class _CapturingRunner:
    def __init__(self, result: MCPRunResult, inputs: list) -> None:
        self._result = result
        self._inputs = inputs

    def call_readonly(self, server, tool, input_data=None, trace_id=None):
        self._inputs.append(input_data)
        return self._result


def _patch_llm_mcp_intent(monkeypatch, tool_name: str, input_json: dict) -> None:
    """Patch the LLM mock client to emit an mcp intent with the given tool_name."""
    from safecode.agent.schemas import AgentToolIntentResponse
    from safecode.agent.tools import ToolIntent

    def fake_choose_tool(self, goal, context):
        return AgentToolIntentResponse(
            intent=ToolIntent(type="mcp", tool_name=tool_name, input_json=input_json),
            rationale="test mcp intent",
        )

    monkeypatch.setattr(
        "safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool
    )


def _patch_mcp_executor(
    monkeypatch,
    *,
    observation: str,
    success: bool,
    blocked: bool = False,
    exit_code: int = 0,
) -> None:
    """Patch MCPReadToolExecutor.execute to return a controlled MCPLoopResult."""

    def fake_execute(self, tool_name, input_json=None, trace_id=None):
        server, tool = tool_name.split(".", 1) if "." in tool_name else ("", tool_name)
        return MCPLoopResult(
            tool_name=tool_name,
            server=server,
            tool=tool,
            observation=observation,
            success=success,
            blocked=blocked,
            exit_code=exit_code if success else 1,
            metadata={"classification": "read"},
        )

    monkeypatch.setattr(
        "safecode.agent.loop.MCPReadToolExecutor.execute", fake_execute
    )
