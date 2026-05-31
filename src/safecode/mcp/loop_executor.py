"""MCP read-only tool executor for the agent loop (v2.2.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.mcp.runner import MCPReadOnlyRunner, classify_mcp_tool
from safecode.tools.adapter import AdapterError, ToolCallAdapter


@dataclass(frozen=True)
class MCPLoopResult:
    """Outcome of an MCP read-only loop execution step."""

    tool_name: str
    server: str
    tool: str
    observation: str
    success: bool
    blocked: bool
    exit_code: int
    metadata: dict[str, str] = field(default_factory=dict)


class MCPReadToolExecutor:
    """Execute approved read-only MCP tool calls inside the agent loop.

    All calls are validated through ToolCallAdapter before execution.
    Fails closed for unknown tools, non-read-only tools, invalid input, or runner errors.
    Never raises — all failure paths return a blocked MCPLoopResult.
    """

    def __init__(
        self, project_root: Path, runner: MCPReadOnlyRunner | None = None
    ) -> None:
        self.project_root = project_root
        self._runner = runner
        self._adapter = ToolCallAdapter()

    def execute(
        self,
        tool_name: str,
        input_json: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> MCPLoopResult:
        """Validate and execute a read-only MCP tool call.

        Validate through ToolCallAdapter, classify the tool, call the runner,
        and return the result as an observation. Never raises.
        """
        input_data = input_json or {}

        try:
            self._adapter.validate(
                "mcp.call_readonly",
                {"tool_name": tool_name, "input_json": input_data},
            )
        except AdapterError as exc:
            return self._fail(tool_name, "", "", f"Adapter validation failed: {exc}", exit_code=126)

        server, tool = _parse_tool_name(tool_name)
        if not server:
            return self._fail(
                tool_name, "", tool_name,
                "MCP tool_name must be 'server.tool' format.",
                exit_code=126,
            )

        classification = classify_mcp_tool(tool)
        if classification != "read":
            return self._fail(
                tool_name, server, tool,
                f"MCP tool '{tool}' is not read-only (classification: {classification}).",
                exit_code=126,
            )

        try:
            runner = self._runner or MCPReadOnlyRunner(self.project_root)
            result = runner.call_readonly(server, tool, input_data, trace_id=trace_id)
        except Exception as exc:
            return self._fail(tool_name, server, tool, f"MCP runner error: {exc}", exit_code=1)

        if result.blocked:
            return MCPLoopResult(
                tool_name=tool_name,
                server=server,
                tool=tool,
                observation=result.error or "MCP call blocked.",
                success=False,
                blocked=True,
                exit_code=result.exit_code,
                metadata={"classification": result.classification},
            )

        observation = result.output or result.error or "MCP call returned no output."
        return MCPLoopResult(
            tool_name=tool_name,
            server=server,
            tool=tool,
            observation=observation,
            success=result.exit_code == 0,
            blocked=False,
            exit_code=result.exit_code,
            metadata={"classification": result.classification},
        )

    def _fail(
        self,
        tool_name: str,
        server: str,
        tool: str,
        reason: str,
        *,
        exit_code: int,
    ) -> MCPLoopResult:
        return MCPLoopResult(
            tool_name=tool_name,
            server=server,
            tool=tool,
            observation=reason,
            success=False,
            blocked=True,
            exit_code=exit_code,
            metadata={},
        )


def _parse_tool_name(tool_name: str) -> tuple[str, str]:
    """Split 'server.tool' into (server, tool). Returns ('', original) on failure."""
    parts = tool_name.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "", tool_name
    return parts[0], parts[1]
