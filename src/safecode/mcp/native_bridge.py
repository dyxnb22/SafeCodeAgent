"""MCP native tool bridge — wraps MCP tools as NativeToolSpecs (v5.4.0/v5.4.1).

Bridges the MCP read-only runner into NativeToolDispatcher so MCP tools
appear as native tools in the agent's tool list.

Tool name policy: ``mcp_<server>_<tool>`` — avoids conflicts with built-in
tools (read_file, edit_file, etc.).

Safety invariants (unchanged from MCPReadOnlyRunner):
- MCP tool outputs pass through redact_secrets() before model context.
- Classification gate (classify_mcp_tool) runs before every call.
- Write-class MCP tools are only registered for scope="write_proposal_required"
  servers, and always require approval (v5.4.1).
- scope="denied" servers are never registered.
- scope="read_only" servers only expose read-class tools.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.context.redactor import redact_secrets
from safecode.mcp.config import MCPConfigStore
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.mcp.schema import classify_with_schema

# Marker placed in NativeToolResult.metadata for write-proposal results (v5.4.1).
MCP_WRITE_PROPOSAL_KEY = "mcp_write_proposal_id"


def _mcp_native_name(server: str, tool: str) -> str:
    """Return the prefixed native tool name for an MCP tool."""
    safe_server = server.replace("-", "_").replace(".", "_")
    safe_tool = tool.replace("-", "_").replace(".", "_")
    return f"mcp_{safe_server}_{safe_tool}"


class MCPNativeToolBridge:
    """Wraps one MCP server's tools as NativeToolSpec instances.

    For scope="read_only" servers:
        Only read-classified tools are registered; write/unknown tools are skipped.

    For scope="write_proposal_required" servers (v5.4.1):
        Read tools are registered as usual.
        Write-classified tools are also registered with requires_approval=True.
        When called without approval, the write handler creates a pending
        write proposal and returns status="blocked" with the proposal ID in
        metadata so the shell can surface an approval prompt.

    Outputs are re-redacted after MCPReadOnlyRunner (defence-in-depth).
    """

    def __init__(self, runner: MCPReadOnlyRunner, server: str, *, allow_write: bool = False) -> None:
        self._runner = runner
        self._server = server
        self._allow_write = allow_write  # True for write_proposal_required scope

    def _tool_specs_from_schemas(self) -> list[tuple[NativeToolSpec, str]]:
        """Return (NativeToolSpec, original_tool_name) for each eligible tool."""
        schemas = self._runner._schemas
        server_schemas = [s for s in schemas if not s.server or s.server == self._server]
        results: list[tuple[NativeToolSpec, str]] = []
        for schema in server_schemas:
            classification = classify_with_schema(schema.tool, schemas, server=self._server)
            input_schema: dict[str, Any] = {}
            if schema.args:
                input_schema = {
                    "type": "object",
                    "properties": {arg: {"type": "string"} for arg in schema.args},
                }
            if classification == "read":
                spec = NativeToolSpec(
                    name=_mcp_native_name(self._server, schema.tool),
                    description=(
                        schema.description
                        or f"MCP read tool {schema.tool!r} on server {self._server!r}. [EXPERIMENTAL]"
                    ),
                    input_schema=input_schema,
                    requires_approval=False,
                    audit_event_type="tool_call_mcp_read",
                    experimental=True,
                )
                results.append((spec, schema.tool))
            elif classification == "write" and self._allow_write:
                # v5.4.1: write tools for write_proposal_required scope
                spec = NativeToolSpec(
                    name=_mcp_native_name(self._server, schema.tool),
                    description=(
                        schema.description
                        or f"MCP write tool {schema.tool!r} on server {self._server!r}. Requires approval. [EXPERIMENTAL]"
                    ),
                    input_schema=input_schema,
                    requires_approval=True,
                    audit_event_type="tool_call_mcp_write",
                    experimental=True,
                )
                results.append((spec, schema.tool))
            # unknown-class tools are always skipped
        return results

    def discover_and_register(self, dispatcher: NativeToolDispatcher) -> int:
        """Register all eligible tools for this server with *dispatcher*.

        Returns the count of tools registered.
        """
        pairs = self._tool_specs_from_schemas()
        for spec, original_tool in pairs:
            _s = self._server
            _r = self._runner
            _t = original_tool
            _requires_approval = spec.requires_approval

            def _make_handler(s: str, r: MCPReadOnlyRunner, t: str, needs_approval: bool):
                native_name = _mcp_native_name(s, t)

                def _handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
                    if needs_approval:
                        # v5.4.1: write proposal flow — never execute directly
                        return _handle_mcp_write_proposal(call_id, native_name, s, t, r, inp)
                    # Read-only fast path
                    result = r.call_readonly(s, t, inp)
                    if result.blocked:
                        return NativeToolResult(
                            call_id=call_id,
                            tool_name=native_name,
                            status="blocked",
                            error=result.error or "MCP tool blocked by policy.",
                        )
                    if result.exit_code != 0:
                        return NativeToolResult(
                            call_id=call_id,
                            tool_name=native_name,
                            status="error",
                            error=result.error or "MCP tool call failed.",
                        )
                    output = redact_secrets(result.output) if result.output else None
                    return NativeToolResult(
                        call_id=call_id,
                        tool_name=native_name,
                        status="success",
                        output=output,
                        metadata={
                            "server": s,
                            "tool": t,
                            "duration_ms": result.duration_ms,
                        },
                    )

                return _handler

            dispatcher.register(spec, _make_handler(_s, _r, _t, _requires_approval))
        return len(pairs)


def _handle_mcp_write_proposal(
    call_id: str,
    native_name: str,
    server: str,
    tool: str,
    runner: MCPReadOnlyRunner,
    inp: dict[str, Any],
) -> NativeToolResult:
    """Create a pending MCP write proposal and block execution pending approval (v5.4.1).

    Flow:
    1. Call runner.propose_write() to create a single-use pending proposal.
    2. Return status="blocked" with the proposal ID in metadata so the shell
       can surface an approval prompt.
    3. After user approves, runner.execute_granted_write() consumes the grant.
    """
    try:
        proposal = runner.propose_write(server, tool, inp)
    except PermissionError as exc:
        return NativeToolResult(
            call_id=call_id,
            tool_name=native_name,
            status="blocked",
            error=f"MCP write blocked: {exc}",
        )
    except ValueError as exc:
        return NativeToolResult(
            call_id=call_id,
            tool_name=native_name,
            status="error",
            error=f"MCP write invalid: {exc}",
        )
    return NativeToolResult(
        call_id=call_id,
        tool_name=native_name,
        status="blocked",
        error=f"MCP write tool {tool!r} on server {server!r} requires approval.",
        metadata={
            MCP_WRITE_PROPOSAL_KEY: proposal.proposal_id,
            "server": server,
            "tool": tool,
            "requires_approval": True,
        },
    )


def register_mcp_tools(dispatcher: NativeToolDispatcher, project_root: Path) -> int:
    """Register all configured non-denied MCP read tools with *dispatcher*.

    Called from AgentLoop._build_dispatcher() alongside register_read_tools /
    register_write_tools / register_command_tool.

    Safety contracts:
    - scope="denied" servers are never registered.
    - Disabled servers are never registered.
    - Write-class tools are silently skipped.
    - Any per-server failure emits a RuntimeWarning and continues.

    Returns the total number of tools registered across all servers.
    """
    total = 0
    try:
        servers = MCPConfigStore(project_root).list_servers()
    except Exception as exc:
        warnings.warn(f"MCP tool registration skipped (config error): {exc}", RuntimeWarning, stacklevel=2)
        return 0

    for server_cfg in servers:
        if server_cfg.scope == "denied":
            continue
        if not server_cfg.enabled:
            continue
        allow_write = server_cfg.scope == "write_proposal_required"
        try:
            runner = MCPReadOnlyRunner(project_root)
            bridge = MCPNativeToolBridge(runner, server_cfg.name, allow_write=allow_write)
            total += bridge.discover_and_register(dispatcher)
        except Exception as exc:
            warnings.warn(
                f"MCP native bridge registration failed for server {server_cfg.name!r}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
    return total
