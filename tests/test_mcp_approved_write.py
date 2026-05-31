"""Tests for v2.2.3: MCP approved write execution."""

from __future__ import annotations

import pytest

from safecode.agent.tools import ToolIntentRouter
from safecode.mcp.loop_executor import MCPApprovedWriteExecutor, MCPLoopResult, _parse_tool_name
from safecode.mcp.proposal import MCPWriteProposal, MCPWriteProposalStore
from safecode.mcp.runner import MCPRunResult
from safecode.state.journal import AgentJournalStore


# ── ProposalStore: approve / reject ────────────────────────────────────────────


class TestProposalStoreApproval:
    def _make_proposal(self, tmp_path) -> MCPWriteProposal:
        store = MCPWriteProposalStore(tmp_path)
        return store.create("notion", "create", {"title": "new page"}, "write", "test reason")

    def test_approve_pending_changes_status(self, tmp_path):
        proposal = self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        approved = store.approve_pending(proposal.proposal_id)
        assert approved.status == "approved"
        assert approved.proposal_id == proposal.proposal_id

    def test_approve_persists_status(self, tmp_path):
        proposal = self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        store.approve_pending(proposal.proposal_id)
        loaded = store.load_pending()
        assert loaded is not None
        assert loaded.status == "approved"

    def test_approve_wrong_id_raises(self, tmp_path):
        self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        with pytest.raises(PermissionError, match="mismatch"):
            store.approve_pending("wrong-id")

    def test_approve_no_pending_raises(self, tmp_path):
        store = MCPWriteProposalStore(tmp_path)
        with pytest.raises(PermissionError, match="No pending"):
            store.approve_pending("any-id")

    def test_approve_already_approved_raises(self, tmp_path):
        proposal = self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        store.approve_pending(proposal.proposal_id)
        with pytest.raises(PermissionError, match="not in pending"):
            store.approve_pending(proposal.proposal_id)

    def test_reject_pending_changes_status(self, tmp_path):
        proposal = self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        rejected = store.reject_pending(proposal.proposal_id)
        assert rejected.status == "rejected"

    def test_reject_persists_status(self, tmp_path):
        proposal = self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        store.reject_pending(proposal.proposal_id)
        loaded = store.load_pending()
        assert loaded is not None
        assert loaded.status == "rejected"

    def test_reject_wrong_id_raises(self, tmp_path):
        self._make_proposal(tmp_path)
        store = MCPWriteProposalStore(tmp_path)
        with pytest.raises(PermissionError, match="mismatch"):
            store.reject_pending("wrong-id")

    def test_reject_no_pending_raises(self, tmp_path):
        store = MCPWriteProposalStore(tmp_path)
        with pytest.raises(PermissionError, match="No pending"):
            store.reject_pending("any-id")


# ── MCPApprovedWriteExecutor ───────────────────────────────────────────────────


def _write_approved_proposal(tmp_path, server: str, tool: str) -> MCPWriteProposal:
    """Helper: create and approve a proposal in tmp_path."""
    store = MCPWriteProposalStore(tmp_path)
    proposal = store.create(server, tool, {}, "write", "test")
    return store.approve_pending(proposal.proposal_id)


class TestMCPApprovedWriteExecutor:
    def test_approved_write_executes_and_returns_observation(self, tmp_path, monkeypatch):
        approved = _write_approved_proposal(tmp_path, "notion", "create")
        fake_result = MCPRunResult(
            server="notion", tool="create", classification="write",
            output="Page created.", error="", exit_code=0,
            duration_ms=10, executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeApprovedRunner(fake_result),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute(
            "notion.create", {}, proposal_id=approved.proposal_id
        )
        assert result.success is True
        assert result.blocked is False
        assert "Page created." in result.observation
        assert result.server == "notion"
        assert result.tool == "create"

    def test_approved_write_discards_proposal_after_success(self, tmp_path, monkeypatch):
        approved = _write_approved_proposal(tmp_path, "notion", "create")
        fake_result = MCPRunResult(
            server="notion", tool="create", classification="write",
            output="done", error="", exit_code=0,
            duration_ms=5, executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeApprovedRunner(fake_result),
        )
        MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {}, proposal_id=approved.proposal_id)
        assert MCPWriteProposalStore(tmp_path).load_pending() is None

    def test_unapproved_pending_proposal_is_blocked(self, tmp_path):
        store = MCPWriteProposalStore(tmp_path)
        store.create("notion", "create", {}, "write", "test")
        result = MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {})
        assert result.blocked is True
        assert result.success is False
        assert "not approved" in result.observation

    def test_rejected_proposal_is_blocked(self, tmp_path):
        store = MCPWriteProposalStore(tmp_path)
        proposal = store.create("notion", "create", {}, "write", "test")
        store.reject_pending(proposal.proposal_id)
        result = MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {})
        assert result.blocked is True
        assert "rejected" in result.observation

    def test_no_pending_proposal_is_blocked(self, tmp_path):
        result = MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {})
        assert result.blocked is True
        assert result.success is False
        assert "No pending" in result.observation

    def test_proposal_id_mismatch_blocks(self, tmp_path):
        _write_approved_proposal(tmp_path, "notion", "create")
        result = MCPApprovedWriteExecutor(tmp_path).execute(
            "notion.create", {}, proposal_id="wrong-proposal-id"
        )
        assert result.blocked is True
        assert "mismatch" in result.observation

    def test_server_tool_mismatch_blocks(self, tmp_path):
        _write_approved_proposal(tmp_path, "notion", "create")
        result = MCPApprovedWriteExecutor(tmp_path).execute("repo.delete", {})
        assert result.blocked is True
        assert "mismatch" in result.observation

    def test_invalid_tool_name_format_fails_closed(self, tmp_path):
        result = MCPApprovedWriteExecutor(tmp_path).execute("nodot")
        assert result.blocked is True
        assert "server.tool" in result.observation

    def test_runner_exception_becomes_safe_observation(self, tmp_path, monkeypatch):
        _write_approved_proposal(tmp_path, "notion", "create")
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _ErrorApprovedRunner(RuntimeError("network failure")),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {})
        assert result.blocked is True
        assert result.success is False
        assert "network failure" in result.observation

    def test_runner_blocked_result_is_safe(self, tmp_path, monkeypatch):
        _write_approved_proposal(tmp_path, "notion", "create")
        fake_result = MCPRunResult(
            server="notion", tool="create", classification="write",
            output="", error="MCP server is not configured.", exit_code=126,
            duration_ms=0, executed=False, blocked=True,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeApprovedRunner(fake_result),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {})
        assert result.blocked is True
        assert result.success is False
        assert "MCP server is not configured." in result.observation

    def test_result_is_frozen(self, tmp_path, monkeypatch):
        approved = _write_approved_proposal(tmp_path, "notion", "create")
        fake_result = MCPRunResult(
            server="notion", tool="create", classification="write",
            output="x", error="", exit_code=0,
            duration_ms=1, executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeApprovedRunner(fake_result),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute(
            "notion.create", {}, proposal_id=approved.proposal_id
        )
        with pytest.raises(Exception):
            result.success = True  # type: ignore[misc]

    def test_input_json_none_treated_as_empty_dict(self, tmp_path, monkeypatch):
        _write_approved_proposal(tmp_path, "api", "update")
        captured_inputs: list = []
        fake_result = MCPRunResult(
            server="api", tool="update", classification="write",
            output="ok", error="", exit_code=0,
            duration_ms=5, executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _CapturingApprovedRunner(fake_result, captured_inputs),
        )
        MCPApprovedWriteExecutor(tmp_path).execute("api.update", None)
        assert captured_inputs[0] == {}

    def test_same_input_as_proposal_executes(self, tmp_path, monkeypatch):
        """Execution with the same input that was proposed succeeds."""
        store = MCPWriteProposalStore(tmp_path)
        proposal = store.create("notion", "create", {"title": "page"}, "write", "test")
        store.approve_pending(proposal.proposal_id)
        fake_result = MCPRunResult(
            server="notion", tool="create", classification="write",
            output="created", error="", exit_code=0,
            duration_ms=5, executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeApprovedRunner(fake_result),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute(
            "notion.create", {"title": "page"}, proposal_id=proposal.proposal_id
        )
        assert result.success is True
        assert result.blocked is False

    def test_changed_input_is_blocked(self, tmp_path, monkeypatch):
        """Execution with different input than proposed is blocked before runner is called."""
        store = MCPWriteProposalStore(tmp_path)
        proposal = store.create("notion", "create", {"title": "page"}, "write", "test")
        store.approve_pending(proposal.proposal_id)
        called = []
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _CapturingApprovedRunner(
                MCPRunResult("notion", "create", "write", "x", "", 0, 1, True, False), called
            ),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute(
            "notion.create", {"title": "DIFFERENT"}, proposal_id=proposal.proposal_id
        )
        assert result.blocked is True
        assert "does not match" in result.observation
        assert not called  # runner must not be invoked

    def test_empty_input_matches_empty_proposal(self, tmp_path, monkeypatch):
        """Empty input matches a proposal created with empty input."""
        _write_approved_proposal(tmp_path, "notion", "create")  # created with {}
        fake_result = MCPRunResult(
            server="notion", tool="create", classification="write",
            output="ok", error="", exit_code=0,
            duration_ms=1, executed=True, blocked=False,
        )
        monkeypatch.setattr(
            "safecode.mcp.loop_executor.MCPReadOnlyRunner",
            lambda *a, **kw: _FakeApprovedRunner(fake_result),
        )
        result = MCPApprovedWriteExecutor(tmp_path).execute("notion.create", {})
        assert result.success is True


# ── MCPReadOnlyRunner.execute_approved_write infrastructure failures ────────────


class TestApprovedWriteRunnerInfraFailures:
    def _make_runner(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        return MCPReadOnlyRunner(tmp_path)

    def _patch_past_config(self, monkeypatch, runner) -> None:
        """Patch server config, policy, and network checks so subprocess is reached."""
        from safecode.mcp.config import MCPServerConfig
        from safecode.policy.commands import CommandDecision
        from safecode.shell.risk import RiskLevel, ShellRisk

        monkeypatch.setattr(runner, "_get_server", lambda name: MCPServerConfig(
            name=name, command="mcp-server", enabled=True,
        ))
        fake_decision = CommandDecision(
            command="mcp-server",
            allowed=True,
            requires_approval=False,
            risk=ShellRisk(level=RiskLevel.LOW, tokens=["mcp-server"]),
            reason="allowed",
        )
        monkeypatch.setattr(runner, "_check_command_policy", lambda server: fake_decision)
        monkeypatch.setattr(runner, "_network_block_reason", lambda input_data: None)

    def test_timeout_returns_blocked(self, tmp_path, monkeypatch):
        import subprocess
        runner = self._make_runner(tmp_path)
        self._patch_past_config(monkeypatch, runner)
        monkeypatch.setattr(
            "safecode.mcp.runner.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(cmd="mcp", timeout=5)
            ),
        )
        result = runner.execute_approved_write("notion", "create", {})
        assert result.blocked is True
        assert result.executed is False
        assert result.exit_code == 124

    def test_file_not_found_returns_blocked(self, tmp_path, monkeypatch):
        runner = self._make_runner(tmp_path)
        self._patch_past_config(monkeypatch, runner)
        monkeypatch.setattr(
            "safecode.mcp.runner.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(
                FileNotFoundError("mcp command not found")
            ),
        )
        result = runner.execute_approved_write("notion", "create", {})
        assert result.blocked is True
        assert result.executed is False
        assert result.exit_code == 127

    def test_server_not_configured_returns_blocked(self, tmp_path):
        runner = self._make_runner(tmp_path)
        result = runner.execute_approved_write("nonexistent_server", "create", {})
        assert result.blocked is True

    def test_nonzero_exit_is_not_blocked(self, tmp_path, monkeypatch):
        """Normal tool failure (nonzero exit) is an executed failure, not blocked."""
        class _CompletedProc:
            returncode = 1
            stdout = ""
            stderr = "tool error"

        runner = self._make_runner(tmp_path)
        self._patch_past_config(monkeypatch, runner)
        monkeypatch.setattr(
            "safecode.mcp.runner.subprocess.run",
            lambda *a, **kw: _CompletedProc(),
        )
        result = runner.execute_approved_write("notion", "create", {})
        assert result.blocked is False
        assert result.exit_code == 1


# ── Router: write/unknown tools still propose (unchanged) ──────────────────────


class TestRouterWriteToolsStillPropose:
    def test_create_tool_routes_to_propose(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.create"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False

    def test_delete_tool_routes_to_propose(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "repo.delete"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False

    def test_update_tool_routes_to_propose(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.update"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False

    def test_unknown_tool_routes_to_propose(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.xyzzy"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False

    def test_read_tool_still_routes_readonly(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.search"})
        assert routed.route == "mcp.call_readonly"
        assert routed.executable_now is True


# ── AgentLoop: approved-write execution ───────────────────────────────────────


class TestAgentLoopApprovedWrite:
    def test_approved_write_executes_when_proposal_approved(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _write_approved_proposal(tmp_path, "notion", "create")
        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        _patch_approved_write_executor(monkeypatch, observation="Page created.", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        assert "notion.create" in result.observation
        assert "Page created." in result.observation
        assert result.stopped_for_approval is False

    def test_approved_write_pending_action_route_is_execute(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _write_approved_proposal(tmp_path, "notion", "create")
        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        _patch_approved_write_executor(monkeypatch, observation="done", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        assert result.state.pending_action is not None
        assert result.state.pending_action.get("route") == "mcp.execute_approved_write"

    def test_approved_write_increments_step(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _write_approved_proposal(tmp_path, "notion", "create")
        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        _patch_approved_write_executor(monkeypatch, observation="done", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        assert result.state.current_step == 1

    def test_approved_write_journals_mcp_call_event(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _write_approved_proposal(tmp_path, "notion", "create")
        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        _patch_approved_write_executor(monkeypatch, observation="done", success=True)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        session_id = result.state.session_id
        events = AgentJournalStore(tmp_path).read(session_id)
        mcp_events = [e for e in events if e.type == "mcp_call"]
        assert mcp_events, "Expected mcp_call journal event for approved write"
        payload = mcp_events[0].payload["mcp_call"]
        assert payload["tool_name"] == "notion.create"
        assert payload.get("approved_write") is True

    def test_unapproved_proposal_does_not_execute(self, tmp_path, monkeypatch):
        """Write intent with only a pending (not approved) proposal routes to pending_action."""
        from safecode.agent.loop import AgentLoop

        # Create proposal but do NOT approve it
        store = MCPWriteProposalStore(tmp_path)
        store.create("notion", "create", {}, "write", "test")

        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        called = []
        monkeypatch.setattr(
            "safecode.agent.loop.MCPApprovedWriteExecutor",
            lambda *a, **kw: _RecordingApprovedExecutor(called),
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        # Should route to mcp.propose pending action, not execute
        assert not called
        assert result.state.pending_action is not None
        assert result.state.pending_action.get("route") == "mcp.propose"

    def test_no_proposal_does_not_execute(self, tmp_path, monkeypatch):
        """Write intent with no proposal routes to pending_action (propose)."""
        from safecode.agent.loop import AgentLoop

        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        called = []
        monkeypatch.setattr(
            "safecode.agent.loop.MCPApprovedWriteExecutor",
            lambda *a, **kw: _RecordingApprovedExecutor(called),
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        assert not called
        assert result.state.pending_action is not None
        assert result.state.pending_action.get("route") == "mcp.propose"

    def test_approved_write_blocked_records_last_error(self, tmp_path, monkeypatch):
        from safecode.agent.loop import AgentLoop

        _write_approved_proposal(tmp_path, "notion", "create")
        _patch_llm_mcp_write_intent(monkeypatch, "notion.create", {})
        _patch_approved_write_executor(
            monkeypatch,
            observation="MCP server is not configured.",
            success=False,
            blocked=True,
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="create notion page")

        assert result.state.last_error is not None
        assert "MCP server is not configured." in result.state.last_error

    def test_readonly_mcp_loop_still_works_alongside_approved_write(self, tmp_path, monkeypatch):
        """Read-only MCP path is unaffected by approved-write additions."""
        from safecode.agent.loop import AgentLoop
        from safecode.mcp.loop_executor import MCPLoopResult

        def fake_execute(self, tool_name, input_json=None, trace_id=None):
            server, tool = tool_name.split(".", 1) if "." in tool_name else ("", tool_name)
            return MCPLoopResult(
                tool_name=tool_name, server=server, tool=tool,
                observation="Found results.", success=True, blocked=False,
                exit_code=0, metadata={"classification": "read"},
            )

        monkeypatch.setattr("safecode.agent.loop.MCPReadToolExecutor.execute", fake_execute)
        _patch_llm_mcp_readonly_intent(monkeypatch, "notion.search", {})

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="search notion")

        assert "notion.search" in result.observation
        assert result.stopped_for_approval is False


# ── Helpers ───────────────────────────────────────────────────────────────────


class _FakeApprovedRunner:
    def __init__(self, result: MCPRunResult) -> None:
        self._result = result

    def execute_approved_write(self, server, tool, input_data=None, trace_id=None):
        return self._result


class _ErrorApprovedRunner:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def execute_approved_write(self, server, tool, input_data=None, trace_id=None):
        raise self._exc


class _CapturingApprovedRunner:
    def __init__(self, result: MCPRunResult, inputs: list) -> None:
        self._result = result
        self._inputs = inputs

    def execute_approved_write(self, server, tool, input_data=None, trace_id=None):
        self._inputs.append(input_data)
        return self._result


class _RecordingApprovedExecutor:
    def __init__(self, log: list) -> None:
        self._log = log

    def execute(self, tool_name, input_json=None, proposal_id=None, trace_id=None):
        self._log.append(tool_name)
        raise RuntimeError("should not be called")


def _patch_llm_mcp_write_intent(monkeypatch, tool_name: str, input_json: dict) -> None:
    from safecode.agent.schemas import AgentToolIntentResponse
    from safecode.agent.tools import ToolIntent

    def fake_choose_tool(self, goal, context):
        return AgentToolIntentResponse(
            intent=ToolIntent(type="mcp", tool_name=tool_name, input_json=input_json),
            rationale="test approved write intent",
        )

    monkeypatch.setattr("safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool)


def _patch_llm_mcp_readonly_intent(monkeypatch, tool_name: str, input_json: dict) -> None:
    from safecode.agent.schemas import AgentToolIntentResponse
    from safecode.agent.tools import ToolIntent

    def fake_choose_tool(self, goal, context):
        return AgentToolIntentResponse(
            intent=ToolIntent(type="mcp", tool_name=tool_name, input_json=input_json),
            rationale="test readonly intent",
        )

    monkeypatch.setattr("safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool)


def _patch_approved_write_executor(
    monkeypatch,
    *,
    observation: str,
    success: bool,
    blocked: bool = False,
    exit_code: int = 0,
) -> None:
    def fake_execute(self, tool_name, input_json=None, proposal_id=None, trace_id=None):
        server, tool = tool_name.split(".", 1) if "." in tool_name else ("", tool_name)
        return MCPLoopResult(
            tool_name=tool_name,
            server=server,
            tool=tool,
            observation=observation,
            success=success,
            blocked=blocked,
            exit_code=exit_code if success else 1,
            metadata={"classification": "write"},
        )

    monkeypatch.setattr("safecode.agent.loop.MCPApprovedWriteExecutor.execute", fake_execute)
