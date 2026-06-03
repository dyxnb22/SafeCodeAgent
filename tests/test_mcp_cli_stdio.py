"""Tests for v3.3.5 — sac mcp stdio-status and sac mcp stdio-discover CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli_mcp import mcp_app
from safecode.mcp.config import MCPServerConfig
from safecode.mcp.discovery import StdioDiscoveryResult
from safecode.mcp.schema import MCPToolSchema


runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server(name: str, *, argv: list[str] | None = None, enabled: bool = True) -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        command=f"run-{name}",
        enabled=enabled,
        argv=tuple(argv) if argv is not None else None,
    )


def _schema(tool: str, server: str = "myserver") -> MCPToolSchema:
    return MCPToolSchema(
        server=server,
        tool=tool,
        classification="unknown",
        description=f"Does {tool}",
        args=(),
    )


# ---------------------------------------------------------------------------
# Help text tests
# ---------------------------------------------------------------------------


class TestHelpText:
    def test_stdio_status_help_mentions_experimental(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-status", "--help"])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()

    def test_stdio_discover_help_mentions_experimental(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-discover", "--help"])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()

    def test_stdio_status_help_mentions_no_subprocess(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-status", "--help"])
        assert result.exit_code == 0
        assert "subprocess" in result.output.lower() or "No subprocess" in result.output

    def test_stdio_discover_help_mentions_no_tools_call(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-discover", "--help"])
        assert result.exit_code == 0
        assert "tools/call" in result.output or "no tools/call" in result.output.lower()

    def test_stdio_status_has_json_option(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-status", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_stdio_discover_has_json_option(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-discover", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_stdio_discover_has_timeout_option(self) -> None:
        result = runner.invoke(mcp_app, ["stdio-discover", "--help"])
        assert result.exit_code == 0
        assert "--timeout" in result.output


# ---------------------------------------------------------------------------
# stdio-status: human output
# ---------------------------------------------------------------------------


class TestStdioStatusHuman:
    def _invoke(self, server: str, servers: list[MCPServerConfig]) -> object:
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
        ):
            mock_store.return_value.list_servers.return_value = servers
            return runner.invoke(mcp_app, ["stdio-status", server])

    def test_server_not_found_exit_1(self) -> None:
        result = self._invoke("missing", [_server("other")])
        assert result.exit_code == 1

    def test_server_not_found_prints_name(self) -> None:
        result = self._invoke("missing", [_server("other")])
        assert "missing" in result.output

    def test_server_not_found_lists_configured(self) -> None:
        result = self._invoke("missing", [_server("other")])
        assert "other" in result.output

    def test_server_not_found_no_servers(self) -> None:
        result = self._invoke("missing", [])
        assert result.exit_code == 1
        assert "missing" in result.output

    def test_stdio_configured_exit_0(self) -> None:
        result = self._invoke("myserver", [_server("myserver", argv=["python", "srv.py"])])
        assert result.exit_code == 0

    def test_stdio_configured_shows_server_name(self) -> None:
        result = self._invoke("myserver", [_server("myserver", argv=["python", "srv.py"])])
        assert "myserver" in result.output

    def test_stdio_configured_shows_experimental(self) -> None:
        result = self._invoke("myserver", [_server("myserver", argv=["python", "srv.py"])])
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()

    def test_stdio_not_configured_exit_0(self) -> None:
        result = self._invoke("myserver", [_server("myserver")])
        assert result.exit_code == 0

    def test_stdio_not_configured_shows_not_configured(self) -> None:
        result = self._invoke("myserver", [_server("myserver")])
        assert "not configured" in result.output.lower() or "not config" in result.output.lower()

    def test_disabled_server_shows_status(self) -> None:
        result = self._invoke("myserver", [_server("myserver", enabled=False)])
        assert result.exit_code == 0
        assert "myserver" in result.output


# ---------------------------------------------------------------------------
# stdio-status: JSON output
# ---------------------------------------------------------------------------


class TestStdioStatusJson:
    def _invoke_json(self, server: str, servers: list[MCPServerConfig]) -> dict:
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
        ):
            mock_store.return_value.list_servers.return_value = servers
            result = runner.invoke(mcp_app, ["stdio-status", server, "--json"])
        return json.loads(result.output)

    def test_not_found_json_status_error(self) -> None:
        data = self._invoke_json("missing", [_server("other")])
        assert data["status"] == "error"

    def test_not_found_json_has_error_field(self) -> None:
        data = self._invoke_json("missing", [_server("other")])
        assert "error" in data
        assert data["error"]

    def test_not_found_json_command_field(self) -> None:
        data = self._invoke_json("missing", [_server("other")])
        assert data["command"] == "mcp stdio-status"

    def test_stdio_configured_json_success(self) -> None:
        data = self._invoke_json("myserver", [_server("myserver", argv=["python", "srv.py"])])
        assert data["status"] == "success"

    def test_stdio_configured_json_true(self) -> None:
        data = self._invoke_json("myserver", [_server("myserver", argv=["python", "srv.py"])])
        assert data["data"]["stdio_configured"] is True

    def test_stdio_not_configured_json_false(self) -> None:
        data = self._invoke_json("myserver", [_server("myserver")])
        assert data["data"]["stdio_configured"] is False

    def test_json_includes_server_name(self) -> None:
        data = self._invoke_json("myserver", [_server("myserver")])
        assert data["data"]["server"] == "myserver"

    def test_json_includes_experimental_flag(self) -> None:
        data = self._invoke_json("myserver", [_server("myserver")])
        assert data["data"]["experimental"] is True

    def test_json_includes_enabled(self) -> None:
        data = self._invoke_json("myserver", [_server("myserver", enabled=False)])
        assert data["data"]["enabled"] is False

    def test_json_null_error_omitted_on_success(self) -> None:
        raw_output = ""
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
        ):
            mock_store.return_value.list_servers.return_value = [_server("myserver")]
            result = runner.invoke(mcp_app, ["stdio-status", "myserver", "--json"])
            raw_output = result.output
        parsed = json.loads(raw_output)
        assert "error" not in parsed or parsed["error"] is None


# ---------------------------------------------------------------------------
# stdio-discover: failure cases (human output)
# ---------------------------------------------------------------------------


class TestStdioDiscoverFailures:
    def _invoke(self, server: str, servers: list[MCPServerConfig]) -> object:
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
        ):
            mock_store.return_value.list_servers.return_value = servers
            return runner.invoke(mcp_app, ["stdio-discover", server])

    def test_server_not_found_exit_1(self) -> None:
        result = self._invoke("missing", [_server("other")])
        assert result.exit_code == 1

    def test_no_argv_exit_1(self) -> None:
        result = self._invoke("myserver", [_server("myserver")])
        assert result.exit_code == 1

    def test_no_argv_prints_error(self) -> None:
        result = self._invoke("myserver", [_server("myserver")])
        assert "argv" in result.output.lower() or "stdio" in result.output.lower()

    def test_transport_failure_exit_1(self) -> None:
        fail_result = StdioDiscoveryResult(
            success=False, error="connection refused", server_name="myserver"
        )
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", return_value=fail_result),
        ):
            mock_store.return_value.list_servers.return_value = [
                _server("myserver", argv=["python", "srv.py"])
            ]
            result = runner.invoke(mcp_app, ["stdio-discover", "myserver"])
        assert result.exit_code == 1

    def test_transport_failure_prints_error_message(self) -> None:
        fail_result = StdioDiscoveryResult(
            success=False, error="connection refused", server_name="myserver"
        )
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", return_value=fail_result),
        ):
            mock_store.return_value.list_servers.return_value = [
                _server("myserver", argv=["python", "srv.py"])
            ]
            result = runner.invoke(mcp_app, ["stdio-discover", "myserver"])
        assert "connection refused" in result.output


# ---------------------------------------------------------------------------
# stdio-discover: success (human output)
# ---------------------------------------------------------------------------


class TestStdioDiscoverSuccess:
    def _invoke(self, schemas: list[MCPToolSchema], skipped: int = 0) -> object:
        disc_result = StdioDiscoveryResult(
            success=True,
            schemas=tuple(schemas),
            skipped_count=skipped,
            server_name="myserver",
        )
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", return_value=disc_result),
        ):
            mock_store.return_value.list_servers.return_value = [
                _server("myserver", argv=["python", "srv.py"])
            ]
            return runner.invoke(mcp_app, ["stdio-discover", "myserver"])

    def test_success_exit_0(self) -> None:
        result = self._invoke([_schema("read_file")])
        assert result.exit_code == 0

    def test_shows_tool_name(self) -> None:
        result = self._invoke([_schema("read_file")])
        assert "read_file" in result.output

    def test_shows_experimental_label(self) -> None:
        result = self._invoke([_schema("read_file")])
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()

    def test_shows_no_tools_call_note(self) -> None:
        result = self._invoke([_schema("read_file")])
        assert "tools/call" in result.output

    def test_empty_tools_exit_0(self) -> None:
        result = self._invoke([])
        assert result.exit_code == 0

    def test_empty_tools_shows_no_tools(self) -> None:
        result = self._invoke([])
        assert "no tools" in result.output.lower()

    def test_skipped_shown_when_nonzero(self) -> None:
        result = self._invoke([_schema("read_file")], skipped=3)
        assert "3" in result.output or "skip" in result.output.lower()

    def test_skipped_not_shown_when_zero(self) -> None:
        result = self._invoke([_schema("read_file")], skipped=0)
        assert "skipped" not in result.output.lower() or "0" not in result.output

    def test_multiple_tools_all_shown(self) -> None:
        result = self._invoke([_schema("read_file"), _schema("write_file"), _schema("list_dir")])
        assert "read_file" in result.output
        assert "write_file" in result.output
        assert "list_dir" in result.output


# ---------------------------------------------------------------------------
# stdio-discover: JSON output
# ---------------------------------------------------------------------------


class TestStdioDiscoverJson:
    def _invoke_json(
        self,
        schemas: list[MCPToolSchema],
        success: bool = True,
        error: str = "",
        skipped: int = 0,
    ) -> dict:
        disc_result = StdioDiscoveryResult(
            success=success,
            schemas=tuple(schemas),
            error=error,
            skipped_count=skipped,
            server_name="myserver",
        )
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", return_value=disc_result),
        ):
            mock_store.return_value.list_servers.return_value = [
                _server("myserver", argv=["python", "srv.py"])
            ]
            result = runner.invoke(mcp_app, ["stdio-discover", "myserver", "--json"])
        return json.loads(result.output)

    def test_success_status(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["status"] == "success"

    def test_command_field(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["command"] == "mcp stdio-discover"

    def test_tools_list_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file"), _schema("write_file")])
        assert len(data["data"]["tools"]) == 2

    def test_tool_names_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["data"]["tools"][0]["tool"] == "read_file"

    def test_tools_found_count(self) -> None:
        data = self._invoke_json([_schema("read_file"), _schema("write_file")])
        assert data["data"]["tools_found"] == 2

    def test_skipped_count_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file")], skipped=2)
        assert data["data"]["skipped"] == 2

    def test_server_name_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["data"]["server"] == "myserver"

    def test_experimental_flag_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["data"]["experimental"] is True

    def test_failure_status_error(self) -> None:
        data = self._invoke_json([], success=False, error="timed out")
        assert data["status"] == "error"

    def test_failure_has_error_field(self) -> None:
        data = self._invoke_json([], success=False, error="timed out")
        assert "error" in data and data["error"]

    def test_failure_tools_empty(self) -> None:
        data = self._invoke_json([], success=False, error="timed out")
        assert data["data"]["tools"] == []

    def test_empty_tools_success(self) -> None:
        data = self._invoke_json([])
        assert data["status"] == "success"
        assert data["data"]["tools"] == []
        assert data["data"]["tools_found"] == 0

    def test_no_argv_json_error(self) -> None:
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
        ):
            mock_store.return_value.list_servers.return_value = [_server("myserver")]
            result = runner.invoke(mcp_app, ["stdio-discover", "myserver", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_tool_classification_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["data"]["tools"][0]["classification"] == "unknown"

    def test_tool_description_in_data(self) -> None:
        data = self._invoke_json([_schema("read_file")])
        assert data["data"]["tools"][0]["description"] == "Does read_file"
