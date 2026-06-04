"""MCP tool executors for the agent loop (v2.2.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.mcp.proposal import MCPWriteProposalStore
from safecode.mcp.runner import MCPReadOnlyRunner, classify_mcp_tool
from safecode.mcp.schema import MCPToolSchema, classify_with_schema
from safecode.core.failure_category import FailureCategory
from safecode.logs.runtime import RuntimeLogger
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
        self,
        project_root: Path,
        runner: MCPReadOnlyRunner | None = None,
        schemas: list[MCPToolSchema] | None = None,
    ) -> None:
        self.project_root = project_root
        self._runner = runner
        self._schemas: list[MCPToolSchema] = schemas or []
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
            return self._fail(tool_name, "", "", f"Adapter validation failed: {exc}", exit_code=126, category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value)

        server, tool = _parse_tool_name(tool_name)
        if not server:
            return self._fail(
                tool_name, "", tool_name,
                "MCP tool_name must be 'server.tool' format.",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        classification = classify_with_schema(tool, self._schemas, server=server)
        if classification != "read":
            return self._fail(
                tool_name, server, tool,
                f"MCP tool '{tool}' is not read-only (classification: {classification}).",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        try:
            runner = self._runner or MCPReadOnlyRunner(self.project_root)
            result = runner.call_readonly(server, tool, input_data, trace_id=trace_id)
        except Exception as exc:
            self._log_failure(tool_name, f"MCP runner error: {exc}", 1, FailureCategory.UNKNOWN.value)
            return self._fail(tool_name, server, tool, f"MCP runner error: {exc}", exit_code=1, category=FailureCategory.UNKNOWN.value)

        if result.blocked:
            self._log_failure(tool_name, result.error or "MCP call blocked.", result.exit_code, FailureCategory.COMMAND_BLOCKED_BY_POLICY.value)
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
        category: str = FailureCategory.UNKNOWN.value,
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

    def _log_failure(self, tool_name: str, message: str, exit_code: int, category: str) -> None:
        try:
            RuntimeLogger(self.project_root).write(
                "error",
                "mcp.loop_executor",
                message,
                failure_category=category,
                details={"command": tool_name, "exit_code": str(exit_code)},
            )
        except Exception:
            pass


class MCPApprovedWriteExecutor:
    """Execute MCP write tool calls that have been explicitly approved through the proposal flow.

    Validates the stored proposal is approved and matches the requested tool before
    calling execute_approved_write on the runner. Discards the proposal after execution.
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
        proposal_id: str | None = None,
        trace_id: str | None = None,
    ) -> MCPLoopResult:
        """Validate approval and execute an approved MCP write tool call.

        Validates via ToolCallAdapter, checks the stored proposal is approved and
        matches the requested tool, runs the tool, then discards the proposal.
        Never raises.
        """
        input_data = input_json or {}

        try:
            self._adapter.validate(
                "mcp.propose_write",
                {"tool_name": tool_name, "input_json": input_data},
            )
        except AdapterError as exc:
            return self._fail(tool_name, "", "", f"Adapter validation failed: {exc}", exit_code=126, category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value)

        server, tool = _parse_tool_name(tool_name)
        if not server:
            return self._fail(
                tool_name, "", tool_name,
                "MCP tool_name must be 'server.tool' format.",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        store = MCPWriteProposalStore(self.project_root)
        proposal = store.load_pending()

        if proposal is None:
            return self._fail(tool_name, server, tool, "No pending MCP write proposal found.", exit_code=126, category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value)

        if proposal.status == "rejected":
            return self._fail(
                tool_name, server, tool,
                f"MCP write proposal was rejected (proposal_id: {proposal.proposal_id}).",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        if proposal.status != "approved":
            return self._fail(
                tool_name, server, tool,
                f"MCP write proposal is not approved (status: {proposal.status}).",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        if proposal_id is not None and proposal.proposal_id != proposal_id:
            return self._fail(tool_name, server, tool, "Proposal ID mismatch.", exit_code=126, category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value)

        if proposal.server != server or proposal.tool != tool:
            return self._fail(
                tool_name, server, tool,
                f"Tool/server mismatch with approved proposal ({proposal.server}.{proposal.tool}).",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        # Verify execution input matches what was reviewed and approved.
        execution_hash = MCPWriteProposalStore.hash_input(
            store._redact_input(input_data)
        )
        if execution_hash != proposal.input_hash:
            return self._fail(
                tool_name, server, tool,
                "Execution input does not match the approved proposal input.",
                exit_code=126,
                category=FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            )

        try:
            runner = self._runner or MCPReadOnlyRunner(self.project_root)
            result = runner.execute_approved_write(server, tool, input_data, trace_id=trace_id)
        except Exception as exc:
            self._log_failure(tool_name, f"MCP runner error: {exc}", 1, FailureCategory.UNKNOWN.value)
            return self._fail(tool_name, server, tool, f"MCP runner error: {exc}", exit_code=1, category=FailureCategory.UNKNOWN.value)

        # Discard proposal after execution regardless of outcome.
        try:
            store.discard_pending()
        except Exception:
            pass

        if result.blocked:
            self._log_failure(tool_name, result.error or "MCP approved write blocked.", result.exit_code, FailureCategory.COMMAND_BLOCKED_BY_POLICY.value)
            return MCPLoopResult(
                tool_name=tool_name,
                server=server,
                tool=tool,
                observation=result.error or "MCP approved write blocked.",
                success=False,
                blocked=True,
                exit_code=result.exit_code,
                metadata={"classification": result.classification},
            )

        observation = result.output or result.error or "MCP approved write returned no output."
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
        category: str = FailureCategory.UNKNOWN.value,
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

    def _log_failure(self, tool_name: str, message: str, exit_code: int, category: str) -> None:
        try:
            RuntimeLogger(self.project_root).write(
                "error",
                "mcp.loop_executor",
                message,
                failure_category=category,
                details={"command": tool_name, "exit_code": str(exit_code)},
            )
        except Exception:
            pass


def _parse_tool_name(tool_name: str) -> tuple[str, str]:
    """Split 'server.tool' into (server, tool). Returns ('', original) on failure."""
    parts = tool_name.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "", tool_name
    return parts[0], parts[1]
