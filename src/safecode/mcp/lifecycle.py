"""MCP server lifecycle management (v3.8.0).

Provides start / stop / restart for background stdio MCP server processes.
PID files are stored under ``{project_root}/{sac_dir}/mcp/<server>.pid``.

Each transition emits both a ``RuntimeLogger`` event and an ``AuditEvent``.
``stop()`` is idempotent and never raises on missing or dead processes.

Status: experimental — lifecycle commands not promoted to stable contract.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.logs.runtime import RuntimeLogger
from safecode.mcp.config import MCPConfigStore, StdioArgvError, resolve_stdio_argv
from safecode.utils.time import utc_now_iso

_DEFAULT_LIFECYCLE_TIMEOUT: float = 10.0


@dataclass(frozen=True)
class MCPLifecycleResult:
    """Result of a lifecycle operation on an MCP server process."""

    server: str
    action: str  # "start" | "stop" | "restart"
    success: bool
    message: str
    pid: int | None = None


class MCPLifecycleManager:
    """Manage start/stop/restart of background stdio MCP server processes.

    PID files live at ``{sac_dir}/mcp/{server}.pid`` inside the project root.
    All transitions emit a RuntimeLogger event and an AuditEvent.
    ``stop()`` is idempotent: returns success even if the server is not running.
    """

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self._pid_dir = project_root / self.config.sac_dir / "mcp"
        self.audit_logger = AuditLogger(project_root, self.config)
        self.runtime_logger = RuntimeLogger(project_root, self.config)

    def pid_path(self, server: str) -> Path:
        """Return the PID file path for a server."""
        return self._pid_dir / f"{server}.pid"

    def read_pid(self, server: str) -> int | None:
        """Return the tracked PID for a server, or None if no PID file exists."""
        p = self.pid_path(server)
        if not p.exists():
            return None
        try:
            return int(p.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None

    def is_running(self, server: str) -> bool:
        """Return True if the server's tracked PID is alive."""
        pid = self.read_pid(server)
        return pid is not None and _pid_alive(pid)

    def start(
        self, server_name: str, *, timeout: float = _DEFAULT_LIFECYCLE_TIMEOUT
    ) -> MCPLifecycleResult:
        """Start a configured MCP server process.

        Returns success (with existing PID) if the process is already running.
        Emits a RuntimeLogger event and an audit event.
        """
        servers = MCPConfigStore(self.project_root).list_servers()
        try:
            argv = resolve_stdio_argv(servers, server_name)
        except StdioArgvError:
            msg = f"Cannot start '{server_name}': stdio argv not configured"
            self.runtime_logger.error("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_start_failed", server_name, "failed", msg)
            return MCPLifecycleResult(server=server_name, action="start", success=False, message=msg)

        existing_pid = self.read_pid(server_name)
        if existing_pid is not None and _pid_alive(existing_pid):
            msg = f"Server '{server_name}' already running (pid={existing_pid})"
            self.runtime_logger.info("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_start_skipped", server_name, "success", msg, pid=existing_pid)
            return MCPLifecycleResult(
                server=server_name, action="start", success=True, message=msg, pid=existing_pid
            )

        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError) as exc:
            msg = f"Failed to start '{server_name}': process could not be launched"
            self.runtime_logger.error("mcp.lifecycle", msg, exc=exc)
            self._audit("mcp_lifecycle_start_failed", server_name, "failed", msg)
            return MCPLifecycleResult(server=server_name, action="start", success=False, message=msg)

        self._write_pid(server_name, proc.pid)
        msg = f"Started '{server_name}' (pid={proc.pid})"
        self.runtime_logger.info("mcp.lifecycle", msg)
        self._audit("mcp_lifecycle_started", server_name, "success", msg, pid=proc.pid)
        return MCPLifecycleResult(
            server=server_name, action="start", success=True, message=msg, pid=proc.pid
        )

    def stop(
        self, server_name: str, *, timeout: float = _DEFAULT_LIFECYCLE_TIMEOUT
    ) -> MCPLifecycleResult:
        """Stop a running MCP server process.

        Idempotent: returns success even if no PID file exists or the process
        is already dead.  Never raises.  Emits a RuntimeLogger event and an
        audit event for every call.
        """
        pid = self.read_pid(server_name)

        if pid is None:
            msg = f"Server '{server_name}' not running (no PID file)"
            self.runtime_logger.info("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_stopped", server_name, "success", msg)
            return MCPLifecycleResult(server=server_name, action="stop", success=True, message=msg)

        if not _pid_alive(pid):
            self._delete_pid(server_name)
            msg = f"Server '{server_name}' already stopped (pid={pid} not alive)"
            self.runtime_logger.info("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_stopped", server_name, "success", msg, pid=pid)
            return MCPLifecycleResult(
                server=server_name, action="stop", success=True, message=msg, pid=pid
            )

        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            self._delete_pid(server_name)
            msg = f"Server '{server_name}' already gone (pid={pid})"
            self.runtime_logger.info("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_stopped", server_name, "success", msg, pid=pid)
            return MCPLifecycleResult(
                server=server_name, action="stop", success=True, message=msg, pid=pid
            )

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not _pid_alive(pid):
                break
            time.sleep(0.05)

        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            _wait_pid_gone(pid, timeout=2.0)

        self._delete_pid(server_name)
        msg = f"Stopped '{server_name}' (pid={pid})"
        self.runtime_logger.info("mcp.lifecycle", msg)
        self._audit("mcp_lifecycle_stopped", server_name, "success", msg, pid=pid)
        return MCPLifecycleResult(
            server=server_name, action="stop", success=True, message=msg, pid=pid
        )

    def restart(
        self, server_name: str, *, timeout: float = _DEFAULT_LIFECYCLE_TIMEOUT
    ) -> MCPLifecycleResult:
        """Stop then start a configured MCP server process."""
        stop_result = self.stop(server_name, timeout=timeout)
        if not stop_result.success:
            msg = f"Restart of '{server_name}' failed at stop step"
            self.runtime_logger.error("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_restart_failed", server_name, "failed", msg)
            return MCPLifecycleResult(
                server=server_name, action="restart", success=False, message=msg
            )

        start_result = self.start(server_name, timeout=timeout)
        if not start_result.success:
            msg = f"Restart of '{server_name}' failed at start step"
            self.runtime_logger.error("mcp.lifecycle", msg)
            self._audit("mcp_lifecycle_restart_failed", server_name, "failed", msg)
            return MCPLifecycleResult(
                server=server_name, action="restart", success=False, message=msg
            )

        msg = f"Restarted '{server_name}' (pid={start_result.pid})"
        self.runtime_logger.info("mcp.lifecycle", msg)
        self._audit(
            "mcp_lifecycle_restarted", server_name, "success", msg, pid=start_result.pid
        )
        return MCPLifecycleResult(
            server=server_name,
            action="restart",
            success=True,
            message=msg,
            pid=start_result.pid,
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _write_pid(self, server: str, pid: int) -> None:
        self._pid_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path(server).write_text(str(pid), encoding="utf-8")

    def _delete_pid(self, server: str) -> None:
        try:
            self.pid_path(server).unlink(missing_ok=True)
        except OSError:
            pass

    def _audit(
        self,
        event_type: str,
        server: str,
        status: str,
        message: str,
        *,
        pid: int | None = None,
    ) -> None:
        metadata: dict[str, str] = {"server": server}
        if pid is not None:
            metadata["pid"] = str(pid)
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status=status,
                message=message,
                metadata=metadata,
            )
        )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    """Return True if the process with the given PID is alive.

    Attempts os.waitpid with WNOHANG first to reap zombie children;
    falls back to os.kill(0) for processes that are not our children.
    """
    try:
        # Try to reap the child (only works if pid is our direct child).
        result = os.waitpid(pid, os.WNOHANG)
        if result[0] != 0:
            return False  # reaped — definitely gone
        # result == (0, 0) means still running
        return True
    except ChildProcessError:
        # Not our child; use the signal-based check.
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
    except OSError:
        return False


def _wait_pid_gone(pid: int, *, timeout: float) -> None:
    """Poll until the PID disappears or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.05)
