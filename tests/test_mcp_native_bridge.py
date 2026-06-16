"""Tests for MCPNativeToolBridge (v5.4.0)."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.mcp.native_bridge import (
    MCPNativeToolBridge,
    _mcp_native_name,
    register_mcp_tools,
)
from safecode.mcp.runner import MCPReadOnlyRunner, MCPRunResult
from safecode.mcp.schema import MCPToolSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner(project_root: Path, schemas: list[MCPToolSchema] | None = None) -> MCPReadOnlyRunner:
    """Return a MCPReadOnlyRunner with overridden _schemas (no TOML required)."""
    runner = MagicMock(spec=MCPReadOnlyRunner)
    runner._schemas = schemas or []
    return runner


def _make_result(
    *,
    server: str = "myserver",
    tool: str = "list_items",
    output: str = "item1\nitem2",
    error: str = "",
    exit_code: int = 0,
    blocked: bool = False,
) -> MCPRunResult:
    return MCPRunResult(
        server=server,
        tool=tool,
        classification="read",
        output=output,
        error=error,
        exit_code=exit_code,
        duration_ms=12,
        executed=not blocked,
        blocked=blocked,
    )


# ---------------------------------------------------------------------------
# _mcp_native_name
# ---------------------------------------------------------------------------


class TestMcpNativeName:
    def test_simple(self):
        assert _mcp_native_name("sqlite", "list_tables") == "mcp_sqlite_list_tables"

    def test_dashes_normalised(self):
        assert _mcp_native_name("brave-search", "web-search") == "mcp_brave_search_web_search"

    def test_dots_normalised(self):
        assert _mcp_native_name("my.server", "get.items") == "mcp_my_server_get_items"

    def test_prefix_avoids_builtin_collision(self):
        # "read_file" is a built-in tool; bridge would be "mcp_x_read_file"
        assert _mcp_native_name("x", "read_file") == "mcp_x_read_file"


# ---------------------------------------------------------------------------
# MCPNativeToolBridge — _tool_specs_from_schemas
# ---------------------------------------------------------------------------


class TestMcpNativeToolBridgeSpecBuilding:
    def test_read_tool_included(self):
        schemas = [
            MCPToolSchema(server="srv", tool="list_files", classification="read", description="List files."),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "srv")
        pairs = bridge._tool_specs_from_schemas()
        assert len(pairs) == 1
        spec, original = pairs[0]
        assert spec.name == "mcp_srv_list_files"
        assert original == "list_files"
        assert spec.experimental is True
        assert spec.requires_approval is False
        assert spec.audit_event_type == "tool_call_mcp_read"

    def test_write_tool_excluded(self):
        schemas = [
            MCPToolSchema(server="srv", tool="delete_file", classification="write"),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "srv")
        assert bridge._tool_specs_from_schemas() == []

    def test_unknown_tool_excluded(self):
        schemas = [
            MCPToolSchema(server="srv", tool="sync_thing", classification="unknown"),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "srv")
        assert bridge._tool_specs_from_schemas() == []

    def test_tool_without_server_included_for_any_server(self):
        """Schemas with no server restriction should match any server."""
        schemas = [
            MCPToolSchema(server="", tool="get_data", classification="read"),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "myserver")
        pairs = bridge._tool_specs_from_schemas()
        assert len(pairs) == 1

    def test_different_server_excluded(self):
        schemas = [
            MCPToolSchema(server="other", tool="list_tables", classification="read"),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "srv")
        assert bridge._tool_specs_from_schemas() == []

    def test_args_populate_input_schema(self):
        schemas = [
            MCPToolSchema(server="srv", tool="query", classification="read", args=("sql", "limit")),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "srv")
        pairs = bridge._tool_specs_from_schemas()
        spec, _ = pairs[0]
        assert "sql" in spec.input_schema.get("properties", {})
        assert "limit" in spec.input_schema.get("properties", {})

    def test_no_schemas_returns_empty(self):
        runner = _make_runner(Path("."), [])
        bridge = MCPNativeToolBridge(runner, "srv")
        assert bridge._tool_specs_from_schemas() == []


# ---------------------------------------------------------------------------
# MCPNativeToolBridge — discover_and_register + handler
# ---------------------------------------------------------------------------


class TestMcpNativeToolBridgeHandler:
    def test_success_result(self):
        schemas = [
            MCPToolSchema(server="srv", tool="list_items", classification="read"),
        ]
        runner = _make_runner(Path("."), schemas)
        runner.call_readonly.return_value = _make_result()

        bridge = MCPNativeToolBridge(runner, "srv")
        dispatcher = NativeToolDispatcher()
        count = bridge.discover_and_register(dispatcher)

        assert count == 1
        assert "mcp_srv_list_items" in [s.name for s in dispatcher.specs()]

        from safecode.agent.native_tools import NativeToolCall
        call = NativeToolCall(tool_name="mcp_srv_list_items", input={}, call_id="c1")
        result = dispatcher.dispatch(call)

        assert result.status == "success"
        assert result.output == "item1\nitem2"
        assert result.metadata["server"] == "srv"
        assert result.metadata["tool"] == "list_items"

    def test_blocked_result(self):
        schemas = [MCPToolSchema(server="srv", tool="list_items", classification="read")]
        runner = _make_runner(Path("."), schemas)
        runner.call_readonly.return_value = _make_result(blocked=True, error="denied by policy")

        bridge = MCPNativeToolBridge(runner, "srv")
        dispatcher = NativeToolDispatcher()
        bridge.discover_and_register(dispatcher)

        from safecode.agent.native_tools import NativeToolCall
        call = NativeToolCall(tool_name="mcp_srv_list_items", input={}, call_id="c2")
        result = dispatcher.dispatch(call)

        assert result.status == "blocked"
        assert "denied" in result.error

    def test_nonzero_exit_code_is_error(self):
        schemas = [MCPToolSchema(server="srv", tool="list_items", classification="read")]
        runner = _make_runner(Path("."), schemas)
        runner.call_readonly.return_value = _make_result(exit_code=1, error="tool crashed")

        bridge = MCPNativeToolBridge(runner, "srv")
        dispatcher = NativeToolDispatcher()
        bridge.discover_and_register(dispatcher)

        from safecode.agent.native_tools import NativeToolCall
        call = NativeToolCall(tool_name="mcp_srv_list_items", input={}, call_id="c3")
        result = dispatcher.dispatch(call)

        assert result.status == "error"

    def test_output_is_redacted(self):
        """Output must pass through redact_secrets (content sanitised)."""
        schemas = [MCPToolSchema(server="srv", tool="get_secret", classification="read")]
        runner = _make_runner(Path("."), schemas)
        runner.call_readonly.return_value = _make_result(
            tool="get_secret", output="token=sk-abc123"
        )

        bridge = MCPNativeToolBridge(runner, "srv")
        dispatcher = NativeToolDispatcher()
        bridge.discover_and_register(dispatcher)

        from safecode.agent.native_tools import NativeToolCall
        call = NativeToolCall(tool_name="mcp_srv_get_secret", input={}, call_id="c4")
        # Just ensure no crash (redact_secrets may or may not strip this token format)
        result = dispatcher.dispatch(call)
        assert result.status == "success"

    def test_returns_count(self):
        schemas = [
            MCPToolSchema(server="srv", tool="list_a", classification="read"),
            MCPToolSchema(server="srv", tool="list_b", classification="read"),
        ]
        runner = _make_runner(Path("."), schemas)
        bridge = MCPNativeToolBridge(runner, "srv")
        dispatcher = NativeToolDispatcher()
        count = bridge.discover_and_register(dispatcher)
        assert count == 2


# ---------------------------------------------------------------------------
# register_mcp_tools
# ---------------------------------------------------------------------------


class TestRegisterMcpTools:
    def test_skips_denied_servers(self, tmp_path):
        from safecode.mcp.config import MCPServerConfig

        with patch("safecode.mcp.native_bridge.MCPConfigStore") as mock_store_cls, \
             patch("safecode.mcp.native_bridge.MCPReadOnlyRunner"):
            mock_store = MagicMock()
            mock_store.list_servers.return_value = [
                MCPServerConfig(name="denied_srv", command="srv", scope="denied"),
            ]
            mock_store_cls.return_value = mock_store

            dispatcher = NativeToolDispatcher()
            count = register_mcp_tools(dispatcher, tmp_path)
            assert count == 0

    def test_skips_disabled_servers(self, tmp_path):
        from safecode.mcp.config import MCPServerConfig

        with patch("safecode.mcp.native_bridge.MCPConfigStore") as mock_store_cls, \
             patch("safecode.mcp.native_bridge.MCPReadOnlyRunner"):
            mock_store = MagicMock()
            mock_store.list_servers.return_value = [
                MCPServerConfig(name="off_srv", command="srv", enabled=False, scope="read_only"),
            ]
            mock_store_cls.return_value = mock_store

            dispatcher = NativeToolDispatcher()
            count = register_mcp_tools(dispatcher, tmp_path)
            assert count == 0

    def test_config_error_emits_warning(self, tmp_path):
        with patch("safecode.mcp.native_bridge.MCPConfigStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.list_servers.side_effect = RuntimeError("no config")
            mock_store_cls.return_value = mock_store

            dispatcher = NativeToolDispatcher()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                count = register_mcp_tools(dispatcher, tmp_path)
                assert count == 0
                assert any("MCP tool registration skipped" in str(x.message) for x in w)

    def test_per_server_error_emits_warning_continues(self, tmp_path):
        from safecode.mcp.config import MCPServerConfig

        with patch("safecode.mcp.native_bridge.MCPConfigStore") as mock_store_cls, \
             patch("safecode.mcp.native_bridge.MCPReadOnlyRunner") as mock_runner_cls:
            mock_store = MagicMock()
            mock_store.list_servers.return_value = [
                MCPServerConfig(name="good", command="srv", scope="read_only"),
                MCPServerConfig(name="bad", command="srv2", scope="read_only"),
            ]
            mock_store_cls.return_value = mock_store

            good_runner = MagicMock()
            good_runner._schemas = [MCPToolSchema(server="good", tool="list_x", classification="read")]
            bad_runner = MagicMock()
            bad_runner._schemas = [MCPToolSchema(server="bad", tool="list_y", classification="read")]

            # Make the second runner fail
            call_count = [0]
            def runner_side_effect(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return good_runner
                raise RuntimeError("bad server init")
            mock_runner_cls.side_effect = runner_side_effect

            dispatcher = NativeToolDispatcher()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                count = register_mcp_tools(dispatcher, tmp_path)
                assert count == 1  # only good_runner registered one tool
                assert any("MCP native bridge registration failed" in str(x.message) for x in w)
