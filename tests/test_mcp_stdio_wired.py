"""v3.8.0 tests: StdioReadOnlyAdapter wired into MCPReadOnlyRunner.

Verifies:
- SAFECODE_MCP_STDIO_RUNNER=1 routes through StdioReadOnlyAdapter when server has argv.
- explicit stdio_runner=True param behaves the same.
- classification gate runs BEFORE stdio call (write/unknown tools never reach adapter).
- server-supplied classification fields in transport responses are ignored.
- flag off (default) is byte-compatible with v3.7.x (uses subprocess shim).
- server without argv falls back to subprocess even when env var is set.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.mcp.config import MCPServerConfig
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.mcp.schema import MCPToolSchema
from safecode.mcp.stdio_runner import StdioCallResult
from safecode.policy.commands import CommandDecision
from safecode.shell.risk import RiskLevel, ShellRisk


# ── Helpers ───────────────────────────────────────────────────────────────────


def _read_schema(server: str, tool: str) -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification="read")


def _write_schema(server: str, tool: str) -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification="write")


def _unknown_schema(server: str, tool: str) -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification="unknown")


def _server_with_argv(name: str) -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        command=name,
        enabled=True,
        argv=("stub-mcp-server", "--server", name),
    )


def _server_no_argv(name: str) -> MCPServerConfig:
    return MCPServerConfig(name=name, command=name, enabled=True, argv=None)


def _make_runner(
    tmp_path: Path,
    schemas: list[MCPToolSchema],
    stdio_runner: bool | None = None,
) -> MCPReadOnlyRunner:
    return MCPReadOnlyRunner(
        project_root=tmp_path,
        schemas=schemas,
        stdio_runner=stdio_runner,
    )


def _allowed_decision(cmd: str = "stub-mcp-server") -> CommandDecision:
    return CommandDecision(
        command=cmd,
        allowed=True,
        reason="allowed",
        requires_approval=False,
        risk=ShellRisk(level=RiskLevel.LOW, tokens=[cmd]),
    )


def _stdio_success(server: str, tool: str, output: str = "ok") -> StdioCallResult:
    return StdioCallResult(
        server=server, tool=tool, classification="read",
        output=output, error="", exit_code=0, success=True, blocked=False,
    )


def _stdio_fail(server: str, tool: str) -> StdioCallResult:
    return StdioCallResult(
        server=server, tool=tool, classification="read",
        output="", error="transport error", exit_code=1, success=False, blocked=False,
    )


# ── Class: TestStdioRunnerFlagOff ─────────────────────────────────────────────


class TestStdioRunnerFlagOff:
    """When stdio_runner is off, behaviour is identical to v3.7.x."""

    def test_default_runner_not_stdio(self, tmp_path):
        runner = MCPReadOnlyRunner(project_root=tmp_path, stdio_runner=False)
        assert runner._stdio_runner is False

    def test_env_zero_disables_stdio(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_MCP_STDIO_RUNNER", "0")
        runner = MCPReadOnlyRunner(project_root=tmp_path)
        assert runner._stdio_runner is False

    def test_env_unset_disables_stdio(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_MCP_STDIO_RUNNER", raising=False)
        runner = MCPReadOnlyRunner(project_root=tmp_path)
        assert runner._stdio_runner is False

    def test_flag_off_never_calls_adapter(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_MCP_STDIO_RUNNER", raising=False)
        schemas = [_read_schema("srv", "get_info")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=False)

        with patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_adapter_cls:
            with patch.object(runner, "_get_server", return_value=None):
                runner.call_readonly("srv", "get_info", {})
            mock_adapter_cls.assert_not_called()


# ── Class: TestStdioRunnerOptIn ───────────────────────────────────────────────


class TestStdioRunnerOptIn:
    """When stdio_runner is on, read-only calls route through StdioReadOnlyAdapter."""

    def test_explicit_true_sets_flag(self, tmp_path):
        runner = MCPReadOnlyRunner(project_root=tmp_path, stdio_runner=True)
        assert runner._stdio_runner is True

    def test_env_one_sets_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_MCP_STDIO_RUNNER", "1")
        runner = MCPReadOnlyRunner(project_root=tmp_path)
        assert runner._stdio_runner is True

    def test_explicit_param_overrides_env_off(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_MCP_STDIO_RUNNER", "0")
        runner = MCPReadOnlyRunner(project_root=tmp_path, stdio_runner=True)
        assert runner._stdio_runner is True

    def test_read_tool_routes_via_adapter(self, tmp_path):
        schemas = [_read_schema("srv", "get_info")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")
        mock_result = _stdio_success("srv", "get_info", "hello world")

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            result = runner.call_readonly("srv", "get_info", {})

        mock_cls.assert_called_once()
        mock_instance.call_readonly.assert_called_once_with("get_info", {})
        assert result.output == "hello world"
        assert result.executed is True
        assert result.blocked is False

    def test_server_without_argv_falls_back_to_subprocess(self, tmp_path):
        schemas = [_read_schema("srv", "get_info")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_no_argv("srv")

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision("srv")), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls, \
             patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"output": "fallback"}'
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            runner.call_readonly("srv", "get_info", {})

        mock_cls.assert_not_called()

    def test_adapter_receives_correct_argv(self, tmp_path):
        schemas = [_read_schema("srv", "list_files")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")
        mock_result = _stdio_success("srv", "list_files", "file1\nfile2")

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            runner.call_readonly("srv", "list_files", {})

        # Verify adapter was called with the server's argv
        mock_cls.assert_called_once()
        call_args = mock_cls.call_args
        argv_passed = call_args[1].get("argv") if call_args[1] else call_args[0][1]
        assert argv_passed == list(server_cfg.argv)

    def test_adapter_receives_schemas(self, tmp_path):
        schemas = [_read_schema("srv", "get_info")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")
        mock_result = _stdio_success("srv", "get_info")

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            runner.call_readonly("srv", "get_info", {})

        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert "schemas" in call_kwargs
        assert call_kwargs["schemas"] == schemas


# ── Class: TestClassificationGateBeforeStdio ─────────────────────────────────


class TestClassificationGateBeforeStdio:
    """The static classification gate must run BEFORE any stdio call."""

    def test_write_tool_blocked_before_adapter(self, tmp_path):
        schemas = [_write_schema("srv", "delete_file")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)

        with patch.object(runner, "_get_server", return_value=_server_with_argv("srv")), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            result = runner.call_readonly("srv", "delete_file", {})

        mock_cls.assert_not_called()
        assert result.blocked is True
        assert result.classification == "write"

    def test_unknown_tool_blocked_before_adapter(self, tmp_path):
        schemas = [_unknown_schema("srv", "mystery_tool")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)

        with patch.object(runner, "_get_server", return_value=_server_with_argv("srv")), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            result = runner.call_readonly("srv", "mystery_tool", {})

        mock_cls.assert_not_called()
        assert result.blocked is True

    def test_keyword_write_tool_blocked_without_schema(self, tmp_path):
        runner = _make_runner(tmp_path, [], stdio_runner=True)

        with patch.object(runner, "_get_server", return_value=_server_with_argv("srv")), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            result = runner.call_readonly("srv", "delete_resource", {})

        mock_cls.assert_not_called()
        assert result.blocked is True

    def test_classification_gate_runs_with_env_opt_in(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_MCP_STDIO_RUNNER", "1")
        schemas = [_write_schema("srv", "write_file")]
        runner = MCPReadOnlyRunner(project_root=tmp_path, schemas=schemas)
        assert runner._stdio_runner is True

        with patch.object(runner, "_get_server", return_value=_server_with_argv("srv")), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            result = runner.call_readonly("srv", "write_file", {})

        mock_cls.assert_not_called()
        assert result.blocked is True


# ── Class: TestStdioAdapterResultConversion ───────────────────────────────────


class TestStdioAdapterResultConversion:
    """MCPRunResult correctly reflects StdioCallResult outcomes."""

    def test_success_result_maps_output(self, tmp_path):
        schemas = [_read_schema("srv", "get_status")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")
        mock_result = _stdio_success("srv", "get_status", "all good")

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            result = runner.call_readonly("srv", "get_status", {})

        assert result.output == "all good"
        assert result.error == ""
        assert result.executed is True
        assert result.blocked is False
        assert result.exit_code == 0

    def test_transport_failure_maps_error(self, tmp_path):
        schemas = [_read_schema("srv", "get_status")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")
        mock_result = _stdio_fail("srv", "get_status")

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            result = runner.call_readonly("srv", "get_status", {})

        assert result.output == ""
        assert "transport error" in result.error
        assert result.executed is True
        assert result.blocked is False
        assert result.exit_code == 1

    def test_blocked_result_maps_blocked(self, tmp_path):
        schemas = [_read_schema("srv", "get_status")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")

        mock_result = StdioCallResult(
            server="srv", tool="get_status", classification="read",
            output="", error="blocked by adapter", exit_code=126,
            success=False, blocked=True,
        )

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            result = runner.call_readonly("srv", "get_status", {})

        assert result.blocked is True
        assert result.executed is False


# ── Class: TestServerSuppliedClassificationIgnored ───────────────────────────


class TestServerSuppliedClassificationIgnored:
    """Server-supplied classification fields in transport responses are ignored."""

    def test_server_classification_field_does_not_affect_gate(self, tmp_path):
        """Even if the transport result says 'write', our gate uses local classification."""
        schemas = [_read_schema("srv", "get_info")]
        runner = _make_runner(tmp_path, schemas, stdio_runner=True)
        server_cfg = _server_with_argv("srv")

        # Transport returns a result with a different classification (server-supplied).
        mock_result = StdioCallResult(
            server="srv", tool="get_info",
            classification="write",  # server-supplied; must be ignored
            output="data", error="", exit_code=0, success=True, blocked=False,
        )

        with patch.object(runner, "_get_server", return_value=server_cfg), \
             patch.object(runner, "_check_command_policy", return_value=_allowed_decision()), \
             patch.object(runner, "_network_block_reason", return_value=None), \
             patch("safecode.mcp.runner.StdioReadOnlyAdapter") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.call_readonly.return_value = mock_result

            result = runner.call_readonly("srv", "get_info", {})

        # MCPRunResult.classification comes from classify_with_schema, not from transport.
        assert result.classification == "read"
        assert result.output == "data"
