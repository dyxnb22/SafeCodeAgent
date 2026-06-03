"""Discover tools from configured MCP servers.

This version intentionally does not launch arbitrary external processes. It
exposes configured servers as discoverable entries so permission and audit can
be developed before real MCP process management.

v3.3.2 adds experimental stdio tools/list discovery via call_stdio.
The new surface (StdioDiscoveryResult, discover_stdio_tools) is experimental
and not wired into the existing static MCPDiscovery or runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from safecode.mcp.config import MCPConfigStore
from safecode.mcp.schema import MCPToolSchema
from safecode.mcp.transport_stdio import (
    call_stdio,
)
from safecode.sandbox.network import NetworkPolicy


_DISCOVERY_TIMEOUT_SECONDS: float = 10.0
_DISCOVERY_MAX_OUTPUT_BYTES: int = 256 * 1024


@dataclass(frozen=True)
class MCPTool:
    """A discovered MCP tool placeholder."""

    server: str
    name: str
    risk: str


class MCPDiscovery:
    """List available MCP tools from config."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.network_policy = NetworkPolicy()

    def list_tools(self) -> list[MCPTool]:
        """Return placeholder tools for enabled servers."""
        tools: list[MCPTool] = []
        for server in MCPConfigStore(self.project_root).list_servers():
            if server.enabled:
                tools.append(MCPTool(server=server.name, name=f"{server.name}.list", risk="low"))
        return tools

    def assert_write_allowed(self) -> None:
        """Reject external write operations until explicit MCP policy exists."""
        raise PermissionError("MCP write operations are disabled by SafeCode policy.")


# ── Experimental stdio tools/list discovery (v3.3.2) ─────────────────────────


@dataclass(frozen=True)
class StdioDiscoveryResult:
    """Result of an experimental one-shot stdio tools/list discovery call.

    Status: experimental. Not wired into MCPDiscovery or runner.

    Attributes
    ----------
    success:
        True only when the transport call succeeded and the response was
        structurally valid (had a "tools" key containing a list).  An empty
        tool list is still success=True.
    schemas:
        Parsed ``MCPToolSchema`` objects, one per valid tool entry returned by
        the server.  Always a tuple; may be empty.  Classification is always
        ``"unknown"`` — callers should pass schemas through
        ``classify_with_schema`` for richer classification.
    error:
        Human-readable failure reason; empty on success.  Never contains argv
        content or caller-supplied params.
    skipped_count:
        Number of individual tool entries skipped due to parse errors (missing
        name, wrong type, etc.).  Meaningful only when ``success=True``.
    server_name:
        The logical server name passed by the caller; used as ``schema.server``
        on all parsed schemas.
    """

    success: bool
    schemas: tuple[MCPToolSchema, ...] = field(default_factory=tuple)
    error: str = ""
    skipped_count: int = 0
    server_name: str = ""


def _parse_tool_entry(entry: object, server_name: str) -> MCPToolSchema | None:
    """Parse one tool entry from a tools/list response.

    Skips (returns None) malformed entries: non-dict, missing or non-string
    name, empty name.  Tolerates absent or wrong-type description and
    inputSchema fields by falling back to safe defaults.

    Never raises; never puts entry content into error text.
    """
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    description = entry.get("description", "")
    if not isinstance(description, str):
        description = ""
    args: tuple[str, ...] = ()
    input_schema = entry.get("inputSchema")
    if isinstance(input_schema, dict):
        props = input_schema.get("properties")
        if isinstance(props, dict):
            args = tuple(k for k in props if isinstance(k, str))
    return MCPToolSchema(
        server=server_name,
        tool=name,
        classification="unknown",
        description=description,
        args=args,
    )


def discover_stdio_tools(
    server_name: str,
    argv: list[str],
    *,
    timeout_seconds: float = _DISCOVERY_TIMEOUT_SECONDS,
    max_output_bytes: int = _DISCOVERY_MAX_OUTPUT_BYTES,
) -> StdioDiscoveryResult:
    """Discover tools from a stdio MCP server via one-shot JSON-RPC tools/list.

    Status: experimental.  Not wired into MCPDiscovery or runner.

    Calls the server process once with method ``"tools/list"`` and no params.
    Individual malformed tool entries are skipped and counted in
    ``skipped_count``.  Transport failures or invalid top-level response
    structure produce ``success=False``.

    Fail-closed rules:

    - Transport error (timeout, bad JSON, process failure) → success=False.
    - Response result not a JSON object → success=False.
    - Response missing ``"tools"`` key → success=False.
    - ``"tools"`` not a list → success=False.
    - Individual entry not a dict, missing name, or non-string name → skipped.
    - Invalid description / inputSchema types → tolerated with safe defaults.

    Parameters
    ----------
    server_name:
        Logical name for the server (used as ``schema.server`` on all results).
    argv:
        Validated process argv.  Must be non-empty; not shell-expanded.
        Caller is responsible for prior validation (e.g. via
        ``validate_stdio_argv`` or ``resolve_stdio_argv``).
    timeout_seconds:
        Passed through to ``call_stdio``.
    max_output_bytes:
        Passed through to ``call_stdio``.

    Returns
    -------
    StdioDiscoveryResult
        ``success=True`` with parsed schemas on success; ``success=False`` with
        error on any transport or structural failure.  Error text never contains
        argv content or server params.
    """
    transport = call_stdio(
        argv,
        "tools/list",
        params=None,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )

    if not transport.success:
        return StdioDiscoveryResult(
            success=False,
            schemas=(),
            error=f"stdio transport failed: {transport.error}",
            skipped_count=0,
            server_name=server_name,
        )

    result_data = transport.result
    if not isinstance(result_data, dict):
        return StdioDiscoveryResult(
            success=False,
            schemas=(),
            error="tools/list response result is not a JSON object",
            skipped_count=0,
            server_name=server_name,
        )

    tools_raw = result_data.get("tools")
    if tools_raw is None:
        return StdioDiscoveryResult(
            success=False,
            schemas=(),
            error="tools/list response missing 'tools' key",
            skipped_count=0,
            server_name=server_name,
        )

    if not isinstance(tools_raw, list):
        return StdioDiscoveryResult(
            success=False,
            schemas=(),
            error="tools/list 'tools' field is not a list",
            skipped_count=0,
            server_name=server_name,
        )

    schemas: list[MCPToolSchema] = []
    skipped = 0
    for entry in tools_raw:
        parsed = _parse_tool_entry(entry, server_name)
        if parsed is None:
            skipped += 1
        else:
            schemas.append(parsed)

    return StdioDiscoveryResult(
        success=True,
        schemas=tuple(schemas),
        error="",
        skipped_count=skipped,
        server_name=server_name,
    )
