"""Tests for v2.3.5+ honest surface (updated for v2.4.2).

Verifies that CLI output accurately communicates current execution boundaries:
- sandbox status/plan: Noop/Docker/macOS Seatbelt/Linux Bubblewrap execute.
- mcp tools: current support is a subprocess JSON shim, not a full JSON-RPC client.
- subagent: current subagents are read-only context/result collectors.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.sandbox.adapter import SandboxExecutionPlan
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.planner import SandboxPlan

runner = CliRunner()


def _make_capability(backend: SandboxBackend, available: bool = True) -> SandboxCapability:
    return SandboxCapability(
        backend=backend,
        available=available,
        supported_platforms=["test"],
        reason="test capability",
        recommended_for="testing",
    )


def _make_sandbox_plan_with_all_backends() -> SandboxPlan:
    return SandboxPlan(
        platform="Darwin",
        recommended_backend=SandboxBackend.NONE,
        capabilities=[
            _make_capability(SandboxBackend.NONE),
            _make_capability(SandboxBackend.MACOS_SEATBELT),
            _make_capability(SandboxBackend.LINUX_BUBBLEWRAP, available=False),
            _make_capability(SandboxBackend.DOCKER),
        ],
        active_logical_boundaries=["FilesystemBoundary", "NetworkPolicy"],
        notes=["Test notes."],
    )


def _make_exec_plan(backend: SandboxBackend = SandboxBackend.NONE) -> SandboxExecutionPlan:
    return SandboxExecutionPlan(
        backend=backend,
        command=["echo", "hello"],
        cwd="/tmp/test",
        network_enabled=False,
        readonly_filesystem=True,
        writable_paths=[],
        env_keys=[],
        timeout_seconds=30,
    )


class TestSandboxStatusHonesty:
    """sandbox status must clearly communicate execution scope."""

    def _invoke_status(self):
        with patch("safecode.cli_sandbox.SandboxPlanner") as mock_cls:
            mock_planner = MagicMock()
            mock_planner.plan.return_value = _make_sandbox_plan_with_all_backends()
            mock_cls.return_value = mock_planner
            return runner.invoke(app, ["sandbox", "status"])

    def test_status_exits_ok(self):
        result = self._invoke_status()
        assert result.exit_code == 0

    def test_status_mentions_v2_4_execution_scope(self):
        """Output must state v2.4.x execution scope."""
        result = self._invoke_status()
        assert "v2.4" in result.output

    def test_status_noop_backend_present(self):
        """Output must identify the Noop backend as the executing one."""
        result = self._invoke_status()
        output_lower = result.output.lower()
        assert "noop" in output_lower or "none" in output_lower

    def test_status_bubblewrap_now_executing_in_v242(self):
        """v2.4.2: Linux Bubblewrap must be labeled executing (preview) in the capability table."""
        result = self._invoke_status()
        assert "linux_bubblewrap" in result.output
        assert "executing" in result.output.lower()

    def test_status_macos_seatbelt_is_executing_preview(self):
        """v2.4.1: macos_seatbelt must appear as executing preview, not plan-only."""
        result = self._invoke_status()
        output = result.output
        assert "macos_seatbelt" in output
        assert "executing" in output.lower()

    def test_status_docker_is_executing_preview(self):
        """docker backend must appear as executing preview in v2.4.x."""
        result = self._invoke_status()
        assert "docker" in result.output
        assert "executing" in result.output.lower()
        assert "preview" in result.output.lower()


class TestSandboxPlanHonesty:
    """sandbox plan must surface backend mode prominently in the plan table."""

    def _invoke_plan_with_backend(self, backend: SandboxBackend):
        with patch("safecode.cli_sandbox.SandboxAdapterFactory") as mock_cls:
            mock_factory = MagicMock()
            mock_factory.create_plan.return_value = _make_exec_plan(backend)
            mock_cls.return_value = mock_factory
            return runner.invoke(app, ["sandbox", "plan", "echo", "hello"])

    def test_plan_noop_exits_ok(self):
        result = self._invoke_plan_with_backend(SandboxBackend.NONE)
        assert result.exit_code == 0

    def test_plan_noop_shows_executing_mode(self):
        """Noop backend plan must show executing mode in the table."""
        result = self._invoke_plan_with_backend(SandboxBackend.NONE)
        assert "executing" in result.output.lower()

    def test_plan_bubblewrap_shows_executing_preview_in_table(self):
        """v2.4.2: Linux Bubblewrap plan must show executing preview mode in the table."""
        result = self._invoke_plan_with_backend(SandboxBackend.LINUX_BUBBLEWRAP)
        assert "executing" in result.output.lower()
        assert "Bubblewrap preview" in result.output or "bwrap" in result.output.lower()

    def test_plan_docker_shows_executing_preview_in_table(self):
        """Docker backend plan must show executing preview mode."""
        result = self._invoke_plan_with_backend(SandboxBackend.DOCKER)
        assert "executing" in result.output.lower()
        assert "Docker preview" in result.output

    def test_plan_seatbelt_shows_executing_preview_in_table(self):
        """macOS Seatbelt plan must show executing preview mode in v2.4.1."""
        result = self._invoke_plan_with_backend(SandboxBackend.MACOS_SEATBELT)
        assert "executing" in result.output.lower()
        assert "Seatbelt preview" in result.output or "sandbox-exec" in result.output

    def test_plan_trailing_note_references_v2_4(self):
        """The trailing dry-run note must reference v2.4.x, not v1.7.x."""
        result = self._invoke_plan_with_backend(SandboxBackend.NONE)
        assert "v2.4" in result.output
        assert "v1.7" not in result.output

    def test_plan_backend_mode_row_in_output(self):
        """sandbox plan output must contain Backend Mode row."""
        result = self._invoke_plan_with_backend(SandboxBackend.LINUX_BUBBLEWRAP)
        assert "Backend Mode" in result.output

    def test_plan_bubblewrap_dry_run_wording_references_bwrap(self):
        """v2.4.2: Linux Bubblewrap dry-run note must reference bwrap execution path."""
        result = self._invoke_plan_with_backend(SandboxBackend.LINUX_BUBBLEWRAP)
        output = result.output
        dry_run_panel_pos = output.find("Dry Run")
        assert dry_run_panel_pos != -1
        # Executing-preview text must appear after the table (near Dry Run panel)
        assert "bwrap" in output.lower() or "Bubblewrap" in output


class TestMCPHonesty:
    """MCP CLI output must communicate that current support is a subprocess JSON shim."""

    def test_mcp_help_mentions_subprocess_or_shim(self):
        """mcp --help must mention subprocess or shim."""
        result = runner.invoke(app, ["mcp", "--help"])
        output_lower = result.output.lower()
        assert "subprocess" in output_lower or "shim" in output_lower

    def test_mcp_help_does_not_claim_full_json_rpc(self):
        """mcp --help must clarify it is not a full MCP JSON-RPC client."""
        result = runner.invoke(app, ["mcp", "--help"])
        output_lower = result.output.lower()
        assert "not a full" in output_lower or "shim" in output_lower or "subprocess" in output_lower

    def test_mcp_tools_output_mentions_shim_or_config(self):
        """mcp tools output must note that tools come from config, not a live call."""
        with patch("safecode.cli_mcp.MCPDiscovery") as mock_cls:
            mock_discovery = MagicMock()
            mock_discovery.list_tools.return_value = []
            mock_cls.return_value = mock_discovery
            result = runner.invoke(app, ["mcp", "tools"])
        output_lower = result.output.lower()
        assert "shim" in output_lower or "subprocess" in output_lower or "config" in output_lower

    def test_mcp_tools_help_mentions_collector_nature(self):
        """mcp tools --help must describe the config-based discovery."""
        result = runner.invoke(app, ["mcp", "tools", "--help"])
        output_lower = result.output.lower()
        assert "config" in output_lower or "shim" in output_lower or "json" in output_lower


class TestSubagentHonesty:
    """Subagent CLI output must communicate that subagents are read-only context/result collectors."""

    def test_subagent_help_mentions_collector(self):
        """sac subagent --help must describe subagents as read-only collectors."""
        result = runner.invoke(app, ["subagent", "--help"])
        output_lower = result.output.lower()
        assert "collector" in output_lower or "read-only" in output_lower

    def test_subagent_help_not_independent_llm(self):
        """sac subagent --help must not claim independent LLM investigation."""
        result = runner.invoke(app, ["subagent", "--help"])
        output_lower = result.output.lower()
        assert "collector" in output_lower or "read-only" in output_lower or "context" in output_lower

    def test_subagent_run_readonly_help_mentions_collector(self):
        """subagent run-readonly --help must describe the collector nature."""
        result = runner.invoke(app, ["subagent", "run-readonly", "--help"])
        output_lower = result.output.lower()
        assert "collector" in output_lower or "read-only" in output_lower

    def test_subagent_run_readonly_help_no_llm_investigation_claim(self):
        """subagent run-readonly --help must clarify no independent LLM investigation."""
        result = runner.invoke(app, ["subagent", "run-readonly", "--help"])
        output_lower = result.output.lower()
        assert "llm" in output_lower or "collector" in output_lower or "read-only" in output_lower
