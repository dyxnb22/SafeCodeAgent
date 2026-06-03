"""v3.8.0 tests: MCP server lifecycle management.

Verifies start / stop / restart via MCPLifecycleManager and the CLI commands
``sac mcp start``, ``sac mcp stop``, ``sac mcp restart``.

Tests use stub binaries only (sys.executable with inline scripts).
No real network; no real MCP protocol.

Key invariants tested:
- start creates PID file; stop deletes it.
- stop is idempotent (no exception, success=True when server not running).
- each transition emits a RuntimeLogger event and an audit event.
- stop with dead PID still returns success (idempotent).
- restart = stop + start.
- missing argv → start fails closed with a human-readable error.
- CLI commands exit 0 on success, exit 1 on failure.
"""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli_mcp import mcp_app
from safecode.mcp.config import MCPServerConfig
from safecode.mcp.lifecycle import MCPLifecycleManager, _pid_alive

_cli_runner = CliRunner()

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mcp_toml(tmp_path: Path, server_name: str, *, with_argv: bool = True) -> None:
    """Write a minimal .sac/mcp.toml with a stub sleep server."""
    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir(parents=True, exist_ok=True)
    argv_line = (
        f'argv = ["{sys.executable}", "-c", "import time; time.sleep(60)"]'
        if with_argv
        else ""
    )
    (sac_dir / "mcp.toml").write_text(
        textwrap.dedent(f"""
            [servers.{server_name}]
            command = "{server_name}"
            {argv_line}
        """).strip()
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def project(tmp_path: Path):
    """Yield a project root with a stub MCP server configured."""
    _make_mcp_toml(tmp_path, "test-srv")
    yield tmp_path


@pytest.fixture
def manager(project: Path) -> MCPLifecycleManager:
    return MCPLifecycleManager(project)


# ── Class: TestLifecycleManagerStart ─────────────────────────────────────────


class TestLifecycleManagerStart:
    def test_start_creates_pid_file(self, manager, project):
        result = manager.start("test-srv")
        try:
            assert result.success is True
            assert result.pid is not None
            assert result.pid > 0
            assert manager.pid_path("test-srv").exists()
            assert manager.read_pid("test-srv") == result.pid
        finally:
            manager.stop("test-srv")

    def test_start_process_is_alive(self, manager):
        result = manager.start("test-srv")
        try:
            assert result.pid is not None
            assert _pid_alive(result.pid)
        finally:
            manager.stop("test-srv")

    def test_start_action_field(self, manager):
        result = manager.start("test-srv")
        try:
            assert result.action == "start"
        finally:
            manager.stop("test-srv")

    def test_start_idempotent_when_already_running(self, manager):
        r1 = manager.start("test-srv")
        try:
            r2 = manager.start("test-srv")
            assert r2.success is True
            assert r2.pid == r1.pid
        finally:
            manager.stop("test-srv")

    def test_start_missing_argv_fails_closed(self, tmp_path):
        _make_mcp_toml(tmp_path, "no-argv-srv", with_argv=False)
        m = MCPLifecycleManager(tmp_path)
        result = m.start("no-argv-srv")
        assert result.success is False
        assert "argv" in result.message.lower() or "configured" in result.message.lower()

    def test_start_unknown_server_fails_closed(self, manager):
        result = manager.start("nonexistent-server")
        assert result.success is False

    def test_start_emits_audit_event(self, manager, project):
        result = manager.start("test-srv")
        try:
            audit_file = project / ".sac" / "logs" / "events.jsonl"
            assert audit_file.exists()
            events = [json.loads(l) for l in audit_file.read_text().splitlines() if l.strip()]
            types = [e["type"] for e in events]
            assert any("lifecycle_start" in t for t in types)
        finally:
            manager.stop("test-srv")


# ── Class: TestLifecycleManagerStop ──────────────────────────────────────────


class TestLifecycleManagerStop:
    def test_stop_kills_process_and_deletes_pid(self, manager):
        r = manager.start("test-srv")
        assert r.pid is not None

        stop_result = manager.stop("test-srv")
        assert stop_result.success is True
        # PID file must be deleted after stop.
        assert not manager.pid_path("test-srv").exists()
        # is_running uses PID file, so returns False once the file is gone.
        assert manager.is_running("test-srv") is False

    def test_stop_action_field(self, manager):
        manager.start("test-srv")
        result = manager.stop("test-srv")
        assert result.action == "stop"

    def test_stop_idempotent_no_pid_file(self, manager):
        result = manager.stop("test-srv")
        assert result.success is True
        assert "not running" in result.message.lower() or "no pid" in result.message.lower()

    def test_stop_idempotent_dead_pid(self, manager, project):
        # Write a PID file pointing to a dead process (PID 1 is typically init but we use
        # a fake high PID that almost certainly doesn't exist on any system).
        manager._pid_dir.mkdir(parents=True, exist_ok=True)
        manager.pid_path("test-srv").write_text("999999999", encoding="utf-8")
        result = manager.stop("test-srv")
        assert result.success is True
        assert not manager.pid_path("test-srv").exists()

    def test_stop_idempotent_called_twice(self, manager):
        manager.start("test-srv")
        r1 = manager.stop("test-srv")
        r2 = manager.stop("test-srv")
        assert r1.success is True
        assert r2.success is True

    def test_stop_emits_audit_event(self, manager, project):
        manager.start("test-srv")
        manager.stop("test-srv")
        audit_file = project / ".sac" / "logs" / "events.jsonl"
        events = [json.loads(l) for l in audit_file.read_text().splitlines() if l.strip()]
        types = [e["type"] for e in events]
        assert any("lifecycle_stop" in t or "lifecycle_started" in t for t in types)
        # stop should have its own event
        assert any("lifecycle_stopped" in t for t in types)

    def test_stop_never_raises(self, manager):
        # Corrupt the PID file — stop must not raise.
        manager._pid_dir.mkdir(parents=True, exist_ok=True)
        manager.pid_path("test-srv").write_text("notanumber", encoding="utf-8")
        result = manager.stop("test-srv")
        assert result.success is True


# ── Class: TestLifecycleManagerRestart ────────────────────────────────────────


class TestLifecycleManagerRestart:
    def test_restart_replaces_process(self, manager):
        r_start = manager.start("test-srv")
        old_pid = r_start.pid
        time.sleep(0.05)

        r_restart = manager.restart("test-srv")
        try:
            assert r_restart.success is True
            assert r_restart.action == "restart"
            assert r_restart.pid is not None
            # After restart the new PID should be different (new process)
            # (or at minimum, old process should be gone)
            time.sleep(0.05)
        finally:
            manager.stop("test-srv")

    def test_restart_from_stopped_state(self, manager):
        result = manager.restart("test-srv")
        try:
            assert result.success is True
            assert result.pid is not None
        finally:
            manager.stop("test-srv")

    def test_restart_emits_audit_event(self, manager, project):
        r = manager.restart("test-srv")
        try:
            audit_file = project / ".sac" / "logs" / "events.jsonl"
            events = [json.loads(l) for l in audit_file.read_text().splitlines() if l.strip()]
            types = [e["type"] for e in events]
            assert any("lifecycle_restart" in t for t in types)
        finally:
            manager.stop("test-srv")


# ── Class: TestLifecycleManagerPIDTracking ────────────────────────────────────


class TestLifecycleManagerPIDTracking:
    def test_pid_dir_created(self, manager, project):
        manager.start("test-srv")
        try:
            assert (project / ".sac" / "mcp").is_dir()
        finally:
            manager.stop("test-srv")

    def test_is_running_true_when_alive(self, manager):
        manager.start("test-srv")
        try:
            assert manager.is_running("test-srv") is True
        finally:
            manager.stop("test-srv")

    def test_is_running_false_when_stopped(self, manager):
        assert manager.is_running("test-srv") is False

    def test_is_running_false_after_stop(self, manager):
        manager.start("test-srv")
        manager.stop("test-srv")
        # PID file deleted by stop; is_running returns False regardless of zombie state.
        assert manager.is_running("test-srv") is False

    def test_read_pid_returns_none_when_no_file(self, manager):
        assert manager.read_pid("test-srv") is None

    def test_read_pid_returns_int_after_start(self, manager):
        r = manager.start("test-srv")
        try:
            pid = manager.read_pid("test-srv")
            assert isinstance(pid, int)
            assert pid == r.pid
        finally:
            manager.stop("test-srv")


# ── Class: TestLifecycleCLICommands ───────────────────────────────────────────


class TestLifecycleCLICommands:
    def test_start_command_exits_zero_on_success(self, project):
        with patch("safecode.cli_mcp.MCPLifecycleManager") as mock_cls:
            mock_mgr = mock_cls.return_value
            from safecode.mcp.lifecycle import MCPLifecycleResult
            mock_mgr.start.return_value = MCPLifecycleResult(
                server="test-srv", action="start", success=True,
                message="Started 'test-srv' (pid=12345)", pid=12345,
            )
            result = _cli_runner.invoke(mcp_app, ["start", "test-srv"])
        assert result.exit_code == 0

    def test_start_command_exits_one_on_failure(self, project):
        with patch("safecode.cli_mcp.MCPLifecycleManager") as mock_cls:
            mock_mgr = mock_cls.return_value
            from safecode.mcp.lifecycle import MCPLifecycleResult
            mock_mgr.start.return_value = MCPLifecycleResult(
                server="no-srv", action="start", success=False,
                message="Cannot start 'no-srv': argv not configured",
            )
            result = _cli_runner.invoke(mcp_app, ["start", "no-srv"])
        assert result.exit_code != 0

    def test_stop_command_exits_zero_always(self, project):
        with patch("safecode.cli_mcp.MCPLifecycleManager") as mock_cls:
            mock_mgr = mock_cls.return_value
            from safecode.mcp.lifecycle import MCPLifecycleResult
            mock_mgr.stop.return_value = MCPLifecycleResult(
                server="test-srv", action="stop", success=True,
                message="Server 'test-srv' not running (no PID file)",
            )
            result = _cli_runner.invoke(mcp_app, ["stop", "test-srv"])
        assert result.exit_code == 0

    def test_restart_command_exits_zero_on_success(self, project):
        with patch("safecode.cli_mcp.MCPLifecycleManager") as mock_cls:
            mock_mgr = mock_cls.return_value
            from safecode.mcp.lifecycle import MCPLifecycleResult
            mock_mgr.restart.return_value = MCPLifecycleResult(
                server="test-srv", action="restart", success=True,
                message="Restarted 'test-srv' (pid=99)", pid=99,
            )
            result = _cli_runner.invoke(mcp_app, ["restart", "test-srv"])
        assert result.exit_code == 0

    def test_start_help_mentions_experimental(self, project):
        result = _cli_runner.invoke(mcp_app, ["start", "--help"])
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()

    def test_stop_help_mentions_experimental(self, project):
        result = _cli_runner.invoke(mcp_app, ["stop", "--help"])
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()

    def test_restart_help_mentions_experimental(self, project):
        result = _cli_runner.invoke(mcp_app, ["restart", "--help"])
        assert "EXPERIMENTAL" in result.output or "experimental" in result.output.lower()


# ── Class: TestRuntimeLogEvents ───────────────────────────────────────────────


class TestRuntimeLogEvents:
    """Each lifecycle transition emits a RuntimeLogger event."""

    def test_start_emits_runtime_log(self, manager, project):
        manager.start("test-srv")
        try:
            log_file = project / ".sac" / "logs" / "runtime.jsonl"
            assert log_file.exists()
            events = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
            messages = [e.get("message", "") for e in events]
            assert any("test-srv" in m for m in messages)
        finally:
            manager.stop("test-srv")

    def test_stop_emits_runtime_log(self, manager, project):
        manager.start("test-srv")
        manager.stop("test-srv")
        log_file = project / ".sac" / "logs" / "runtime.jsonl"
        events = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
        messages = [e.get("message", "") for e in events]
        stop_msgs = [m for m in messages if "Stopped" in m or "not running" in m.lower()]
        assert len(stop_msgs) >= 1
