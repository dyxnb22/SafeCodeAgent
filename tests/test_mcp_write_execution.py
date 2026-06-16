"""Tests for MCP write execution flow (v5.4.1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall
from safecode.mcp.native_bridge import (
    MCPNativeToolBridge,
    MCP_WRITE_PROPOSAL_KEY,
    _handle_mcp_write_proposal,
    _mcp_native_name,
    register_mcp_tools,
)
from safecode.mcp.runner import MCPReadOnlyRunner, MCPRunResult
from safecode.mcp.schema import MCPToolSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner_with_schemas(schemas: list[MCPToolSchema]) -> MCPReadOnlyRunner:
    runner = MagicMock(spec=MCPReadOnlyRunner)
    runner._schemas = schemas
    return runner


def _make_run_result(
    *,
    server="myserver",
    tool="list_items",
    output="result",
    error="",
    exit_code=0,
    blocked=False,
) -> MCPRunResult:
    return MCPRunResult(
        server=server, tool=tool, classification="read",
        output=output, error=error, exit_code=exit_code,
        duration_ms=5, executed=not blocked, blocked=blocked,
    )


# ---------------------------------------------------------------------------
# Bridge: write tool registration for write_proposal_required scope
# ---------------------------------------------------------------------------


class TestWriteToolRegistration:
    def test_write_tool_not_registered_for_read_only_scope(self):
        schemas = [MCPToolSchema(server="srv", tool="delete_item", classification="write")]
        runner = _make_runner_with_schemas(schemas)
        bridge = MCPNativeToolBridge(runner, "srv", allow_write=False)
        pairs = bridge._tool_specs_from_schemas()
        assert pairs == []

    def test_write_tool_registered_for_write_proposal_required(self):
        schemas = [MCPToolSchema(server="srv", tool="delete_item", classification="write")]
        runner = _make_runner_with_schemas(schemas)
        bridge = MCPNativeToolBridge(runner, "srv", allow_write=True)
        pairs = bridge._tool_specs_from_schemas()
        assert len(pairs) == 1
        spec, original = pairs[0]
        assert spec.name == "mcp_srv_delete_item"
        assert spec.requires_approval is True
        assert spec.audit_event_type == "tool_call_mcp_write"
        assert original == "delete_item"

    def test_read_tool_still_registered_alongside_write(self):
        schemas = [
            MCPToolSchema(server="srv", tool="list_items", classification="read"),
            MCPToolSchema(server="srv", tool="delete_item", classification="write"),
        ]
        runner = _make_runner_with_schemas(schemas)
        bridge = MCPNativeToolBridge(runner, "srv", allow_write=True)
        pairs = bridge._tool_specs_from_schemas()
        names = [p[0].name for p in pairs]
        assert "mcp_srv_list_items" in names
        assert "mcp_srv_delete_item" in names

    def test_unknown_tool_always_skipped(self):
        schemas = [MCPToolSchema(server="srv", tool="sync_thing", classification="unknown")]
        runner = _make_runner_with_schemas(schemas)
        bridge = MCPNativeToolBridge(runner, "srv", allow_write=True)
        assert bridge._tool_specs_from_schemas() == []


# ---------------------------------------------------------------------------
# _handle_mcp_write_proposal
# ---------------------------------------------------------------------------


class TestHandleMcpWriteProposal:
    def test_returns_blocked_with_proposal_id(self):
        runner = MagicMock(spec=MCPReadOnlyRunner)
        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "prop-abc123"
        runner.propose_write.return_value = mock_proposal

        result = _handle_mcp_write_proposal(
            call_id="c1",
            native_name="mcp_srv_delete_item",
            server="srv",
            tool="delete_item",
            runner=runner,
            inp={"id": "123"},
        )

        assert result.status == "blocked"
        assert result.metadata[MCP_WRITE_PROPOSAL_KEY] == "prop-abc123"
        assert result.metadata["requires_approval"] is True
        assert result.metadata["server"] == "srv"
        assert result.metadata["tool"] == "delete_item"

    def test_permission_error_returns_blocked(self):
        runner = MagicMock(spec=MCPReadOnlyRunner)
        runner.propose_write.side_effect = PermissionError("scope is denied")

        result = _handle_mcp_write_proposal(
            call_id="c2",
            native_name="mcp_srv_delete",
            server="srv",
            tool="delete",
            runner=runner,
            inp={},
        )

        assert result.status == "blocked"
        assert "denied" in result.error

    def test_value_error_returns_error(self):
        runner = MagicMock(spec=MCPReadOnlyRunner)
        runner.propose_write.side_effect = ValueError("tool is read-only")

        result = _handle_mcp_write_proposal(
            call_id="c3",
            native_name="mcp_srv_get",
            server="srv",
            tool="get",
            runner=runner,
            inp={},
        )

        assert result.status == "error"


# ---------------------------------------------------------------------------
# Write tool handler wired through dispatcher
# ---------------------------------------------------------------------------


class TestWriteToolDispatchHandler:
    def test_write_handler_returns_blocked_with_proposal(self):
        schemas = [MCPToolSchema(server="srv", tool="delete_item", classification="write")]
        runner = _make_runner_with_schemas(schemas)

        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "prop-xyz"
        runner.propose_write.return_value = mock_proposal

        bridge = MCPNativeToolBridge(runner, "srv", allow_write=True)
        dispatcher = NativeToolDispatcher()
        bridge.discover_and_register(dispatcher)

        call = NativeToolCall(tool_name="mcp_srv_delete_item", input={"id": "42"}, call_id="c4")
        result = dispatcher.dispatch(call)

        assert result.status == "blocked"
        assert result.metadata.get(MCP_WRITE_PROPOSAL_KEY) == "prop-xyz"
        runner.propose_write.assert_called_once_with("srv", "delete_item", {"id": "42"})

    def test_read_handler_executes_directly(self):
        schemas = [MCPToolSchema(server="srv", tool="list_items", classification="read")]
        runner = _make_runner_with_schemas(schemas)
        runner.call_readonly.return_value = _make_run_result(output="item1")

        bridge = MCPNativeToolBridge(runner, "srv", allow_write=False)
        dispatcher = NativeToolDispatcher()
        bridge.discover_and_register(dispatcher)

        call = NativeToolCall(tool_name="mcp_srv_list_items", input={}, call_id="c5")
        result = dispatcher.dispatch(call)

        assert result.status == "success"
        runner.call_readonly.assert_called_once()
        # propose_write must not be called for read tools
        runner.propose_write.assert_not_called()


# ---------------------------------------------------------------------------
# register_mcp_tools passes allow_write correctly
# ---------------------------------------------------------------------------


class TestRegisterMcpToolsWriteScope:
    def test_write_proposal_required_enables_write_tools(self, tmp_path):
        from safecode.mcp.config import MCPServerConfig

        with patch("safecode.mcp.native_bridge.MCPConfigStore") as mock_cfg, \
             patch("safecode.mcp.native_bridge.MCPReadOnlyRunner") as mock_runner_cls:
            mock_cfg_inst = MagicMock()
            mock_cfg_inst.list_servers.return_value = [
                MCPServerConfig(name="rw", command="rw-srv", scope="write_proposal_required"),
            ]
            mock_cfg.return_value = mock_cfg_inst

            runner = MagicMock()
            runner._schemas = [
                MCPToolSchema(server="rw", tool="write_data", classification="write"),
            ]
            mock_runner_cls.return_value = runner

            dispatcher = NativeToolDispatcher()
            count = register_mcp_tools(dispatcher, tmp_path)
            assert count == 1
            spec = dispatcher.get_spec("mcp_rw_write_data")
            assert spec is not None
            assert spec.requires_approval is True

    def test_read_only_scope_blocks_write_tools(self, tmp_path):
        from safecode.mcp.config import MCPServerConfig

        with patch("safecode.mcp.native_bridge.MCPConfigStore") as mock_cfg, \
             patch("safecode.mcp.native_bridge.MCPReadOnlyRunner") as mock_runner_cls:
            mock_cfg_inst = MagicMock()
            mock_cfg_inst.list_servers.return_value = [
                MCPServerConfig(name="ro", command="ro-srv", scope="read_only"),
            ]
            mock_cfg.return_value = mock_cfg_inst

            runner = MagicMock()
            runner._schemas = [
                MCPToolSchema(server="ro", tool="write_data", classification="write"),
            ]
            mock_runner_cls.return_value = runner

            dispatcher = NativeToolDispatcher()
            count = register_mcp_tools(dispatcher, tmp_path)
            assert count == 0  # write tool not registered for read_only scope


# ---------------------------------------------------------------------------
# sac mcp execute CLI (smoke test)
# ---------------------------------------------------------------------------


class TestMcpExecuteCli:
    def test_execute_without_grant_blocks(self, tmp_path):
        """execute_granted_write returns blocked when no grant exists."""
        import os
        from typer.testing import CliRunner
        from safecode.cli_mcp import mcp_app

        runner = CliRunner()
        # Use a temp approval dir that has no grants
        env = os.environ.copy()
        env["SAFECODE_MCP_APPROVAL_DIR"] = str(tmp_path / "no_approvals")

        # Create minimal mcp.toml so MCPConfigStore doesn't fail
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        (sac_dir / "mcp.toml").write_text(
            '[servers.testsrv]\ncommand = "echo"\nscope = "write_proposal_required"\n'
        )

        result = runner.invoke(
            mcp_app,
            ["execute", "testsrv", "delete_item", "--grant-id", "nonexistent-grant"],
            catch_exceptions=False,
            env=env,
        )
        # Should fail (no grant, not a stdio-routed server)
        assert result.exit_code != 0

    def test_execute_json_error_output(self, tmp_path):
        """execute --json returns JSON on error."""
        import os
        from typer.testing import CliRunner
        from safecode.cli_mcp import mcp_app

        runner = CliRunner()
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        (sac_dir / "mcp.toml").write_text(
            '[servers.srv]\ncommand = "echo"\nscope = "write_proposal_required"\n'
        )
        env = os.environ.copy()
        env["SAFECODE_MCP_APPROVAL_DIR"] = str(tmp_path / "no_approvals")

        result = runner.invoke(
            mcp_app,
            ["execute", "srv", "write_item", "--grant-id", "bad-id", "--json"],
            catch_exceptions=False,
            env=env,
        )
        assert result.exit_code != 0
        import json
        data = json.loads(result.output)
        assert data["status"] == "error"
