"""Read-only MCP runner with policy enforcement."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.logs.runtime import RuntimeLogger
from safecode.mcp.config import MCPConfigStore, MCPServerConfig
from safecode.policy.commands import CommandDecision, CommandPolicy
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.sandbox.network import NetworkPolicy
from safecode.shell.runner import ShellRunner
from safecode.utils.time import utc_now_iso

READONLY_TOOL_KEYWORDS = {
    "list",
    "get",
    "read",
    "fetch",
    "search",
    "describe",
    "inspect",
    "status",
    "info",
    "query",
}

WRITE_TOOL_KEYWORDS = {
    "write",
    "create",
    "update",
    "delete",
    "remove",
    "set",
    "add",
    "insert",
    "apply",
    "patch",
    "commit",
    "push",
    "post",
    "put",
    "exec",
    "run",
    "merge",
    "approve",
    "grant",
    "revoke",
}


def classify_mcp_tool(name: str) -> str:
    """Classify a tool name as read, write, or unknown."""
    tokens = [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]
    if any(token in WRITE_TOOL_KEYWORDS for token in tokens):
        return "write"
    if any(token in READONLY_TOOL_KEYWORDS for token in tokens):
        return "read"
    return "unknown"


@dataclass(frozen=True)
class MCPRunResult:
    """Outcome of a controlled MCP tool invocation."""

    server: str
    tool: str
    classification: str
    output: str
    error: str
    exit_code: int
    duration_ms: int
    executed: bool
    blocked: bool


class MCPReadOnlyRunner:
    """Run MCP tools with read-only and network boundaries enforced."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.policy = CommandPolicy(self.config)
        self.audit_logger = AuditLogger(project_root, self.config)
        self.runtime_logger = RuntimeLogger(project_root, self.config)
        self.network_policy = NetworkPolicy(self.config)
        FilesystemBoundary(project_root, self.config).validate(project_root)

    def call_readonly(
        self,
        server: str,
        tool: str,
        input_data: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> MCPRunResult:
        """Invoke a tool with the read-only policy."""
        classification = classify_mcp_tool(tool)
        self._audit("mcp_call_proposed", server, tool, classification, "pending", "MCP call proposed", trace_id=trace_id)

        if classification != "read":
            return self._blocked(server, tool, classification, "MCP tool is not classified as read-only.", trace_id)

        server_config = self._get_server(server)
        if not server_config:
            return self._blocked(server, tool, classification, "MCP server is not configured.", trace_id)
        if not server_config.enabled:
            return self._blocked(server, tool, classification, "MCP server is disabled by config.", trace_id)
        if not server_config.command:
            return self._blocked(server, tool, classification, "MCP server command is empty.", trace_id)

        decision = self._check_command_policy(server_config)
        if not decision.allowed:
            exit_code = 125 if decision.requires_approval else 126
            return self._blocked(server, tool, classification, decision.reason, trace_id, exit_code)

        network_block = self._network_block_reason(input_data or {})
        if network_block:
            return self._blocked(server, tool, classification, network_block, trace_id)

        payload = {"tool": tool, "input": input_data or {}}
        payload_text = json.dumps(payload, ensure_ascii=False)
        if len(payload_text) > self._input_limit():
            return self._blocked(server, tool, classification, "MCP input exceeded size limits.", trace_id)

        self._audit("mcp_call_started", server, tool, classification, "started", "MCP call started", trace_id=trace_id)

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                decision.risk.tokens,
                cwd=self.project_root,
                text=True,
                input=payload_text,
                capture_output=True,
                env=ShellRunner(self.project_root, self.config)._sanitized_env(),
                timeout=self.config.shell.default_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = exc.stderr or "MCP call timed out."
            self.runtime_logger.error("mcp.runner", "MCP call timed out", exc=exc, trace_id=trace_id)
            self._audit(
                "mcp_call_completed",
                server,
                tool,
                classification,
                "failed",
                message,
                exit_code=124,
                trace_id=trace_id,
            )
            return MCPRunResult(server, tool, classification, "", message, 124, duration_ms, True, False)
        except FileNotFoundError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = str(exc)
            self.runtime_logger.error("mcp.runner", "MCP command missing", exc=exc, trace_id=trace_id)
            self._audit(
                "mcp_call_completed",
                server,
                tool,
                classification,
                "failed",
                message,
                exit_code=127,
                trace_id=trace_id,
            )
            return MCPRunResult(server, tool, classification, "", message, 127, duration_ms, False, False)

        duration_ms = int((time.perf_counter() - started) * 1000)
        output, output_error = self._extract_output(completed.stdout)
        if output_error:
            self.runtime_logger.error(
                "mcp.runner",
                "MCP tool returned an error payload",
                trace_id=trace_id,
                error=output_error,
            )
        output = redact_secrets(output)
        stderr = redact_secrets(completed.stderr or "")
        if output_error:
            stderr = redact_secrets(output_error)

        if len(output) > self._output_limit():
            message = "MCP output exceeded size limits."
            self.runtime_logger.error("mcp.runner", message, trace_id=trace_id)
            self._audit("mcp_call_blocked", server, tool, classification, "blocked", message, trace_id=trace_id)
            return MCPRunResult(server, tool, classification, "", message, 126, duration_ms, True, True)

        exit_code = completed.returncode
        if output_error and exit_code == 0:
            exit_code = 1

        status = "success" if exit_code == 0 else "failed"
        message = stderr or output or "MCP call completed."
        self._audit(
            "mcp_call_completed",
            server,
            tool,
            classification,
            status,
            message,
            exit_code=exit_code,
            trace_id=trace_id,
        )
        if exit_code != 0:
            self.runtime_logger.error(
                "mcp.runner",
                "MCP call failed",
                trace_id=trace_id,
                exit_code=str(exit_code),
                stderr=stderr,
            )
        return MCPRunResult(server, tool, classification, output, stderr, exit_code, duration_ms, True, False)

    def _get_server(self, name: str) -> MCPServerConfig | None:
        for server in MCPConfigStore(self.project_root).list_servers():
            if server.name == name:
                return server
        return None

    def _check_command_policy(self, server: MCPServerConfig) -> CommandDecision:
        return self.policy.evaluate(server.command, approved=False)

    def _network_block_reason(self, input_data: dict[str, Any]) -> str | None:
        if not self.config.sandbox.network_enabled:
            return "Network access is disabled by policy."
        if self.config.sandbox.network_allowlist:
            target = self._extract_network_target(input_data)
            if not target:
                return "Network access requires an allowlisted host for MCP."
            try:
                self.network_policy.assert_allowed(target)
            except PermissionError as exc:
                return str(exc)
        return None

    def _extract_network_target(self, input_data: dict[str, Any]) -> str | None:
        for key in ("url", "endpoint", "host", "base_url"):
            value = input_data.get(key)
            if isinstance(value, str):
                return self._normalize_network_target(value)
        return None

    def _normalize_network_target(self, token: str) -> str | None:
        if token.startswith(("/", "./", "../")):
            return None
        if "://" in token:
            return token
        if "@" in token and ":" in token:
            user_host, path = token.split(":", 1)
            return f"ssh://{user_host}/{path}"
        return f"https://{token}" if token else None

    def _extract_output(self, stdout: str) -> tuple[str, str | None]:
        raw = stdout.strip()
        if not raw:
            return "", None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw, None
        if isinstance(payload, dict):
            if "error" in payload:
                return "", str(payload.get("error"))
            if "output" in payload:
                return self._stringify_payload(payload.get("output")), None
        return raw, None

    def _stringify_payload(self, payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False)

    def _input_limit(self) -> int:
        return self.config.max_context_chars

    def _output_limit(self) -> int:
        return self.config.max_context_chars

    def _blocked(
        self,
        server: str,
        tool: str,
        classification: str,
        reason: str,
        trace_id: str | None,
        exit_code: int = 126,
    ) -> MCPRunResult:
        self._audit("mcp_call_blocked", server, tool, classification, "blocked", reason, trace_id=trace_id)
        return MCPRunResult(server, tool, classification, "", reason, exit_code, 0, False, True)

    def _audit(
        self,
        event_type: str,
        server: str,
        tool: str,
        classification: str,
        status: str,
        message: str,
        exit_code: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status=status,
                message=message,
                exit_code=exit_code,
                trace_id=trace_id,
                metadata={
                    "server": server,
                    "tool": tool,
                    "classification": classification,
                },
            )
        )
