"""Experimental read-only stdio MCP runner adapter (v3.3.4).

Provides ``StdioReadOnlyAdapter``: a self-contained adapter that calls
``tools/call`` via ``call_stdio`` for tools classified read-only by the
existing schema/classification gate.

Status: experimental.  Not wired into ``MCPReadOnlyRunner`` by default.
Callers must instantiate ``StdioReadOnlyAdapter`` explicitly.

Security properties (inherited from call_stdio + enforced here):
- argv list only; never shell=True.
- Classification gate blocks write and unknown tools before any call.
- Timeout kills the process; exit code 124 on timeout.
- Max output size enforced; fails closed if exceeded.
- call_args content never copied into error text.
- All failures return blocked/failed results — never raises.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Any

from safecode.mcp.schema import MCPToolSchema, classify_with_schema
from safecode.mcp.transport_stdio import (
    _DEFAULT_MAX_OUTPUT_BYTES,
    _DEFAULT_TIMEOUT_SECONDS,
    call_stdio,
)


@dataclass(frozen=True)
class StdioCallResult:
    """Result of an experimental stdio MCP tools/call invocation.

    Attributes
    ----------
    server:
        Logical server name.
    tool:
        Tool name that was called (or attempted).
    classification:
        Classification used at the gate (``"read"``, ``"write"``, or
        ``"unknown"``).
    output:
        Extracted text output from the server; empty on failure or block.
    error:
        Human-readable failure or block reason; empty on success.
        Never contains call_args content.
    exit_code:
        Process exit code, or synthetic: 124=timeout, 126=blocked/size,
        127=not-found.
    success:
        True only when the call completed and transport reported success.
    blocked:
        True when the call was blocked by the classification gate or policy;
        False when the call was attempted (successfully or not).
    """

    server: str
    tool: str
    classification: str
    output: str
    error: str
    exit_code: int
    success: bool
    blocked: bool


class StdioReadOnlyAdapter:
    """Experimental read-only adapter for stdio MCP servers.

    Status: experimental.  Disabled by default — not wired into
    ``MCPReadOnlyRunner``.  Callers must instantiate explicitly.

    Only allows tools classified ``"read"`` by ``classify_with_schema``
    (same gate as the existing runner).  Write and unknown tools are
    blocked before any subprocess is launched.

    All failures return a ``StdioCallResult`` — never raises.
    call_args values are never copied into error text.

    Parameters
    ----------
    server_name:
        Logical MCP server name (used as ``schema.server`` for classification
        and in result metadata).
    argv:
        Validated process argv; caller is responsible for prior validation
        (``validate_stdio_argv`` / ``resolve_stdio_argv``).
    schemas:
        Optional static schemas for classification.  When present,
        ``classify_with_schema`` uses them; falls back to keyword matching
        when absent or when no schema matches the tool.
    timeout_seconds:
        Passed through to ``call_stdio``.
    max_output_bytes:
        Passed through to ``call_stdio``.
    """

    def __init__(
        self,
        server_name: str,
        argv: list[str],
        schemas: list[MCPToolSchema] | None = None,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self.server_name = server_name
        self._argv = argv
        self._schemas: list[MCPToolSchema] = schemas or []
        self._timeout = timeout_seconds
        self._max_output = max_output_bytes

    def call_readonly(
        self,
        tool: str,
        call_args: dict[str, Any] | None = None,
    ) -> StdioCallResult:
        """Call a read-only tool via stdio JSON-RPC ``tools/call``.

        Classifies the tool before calling.  Write and unknown tools are
        blocked immediately.  Transport failures return a non-blocked failure
        result.  All paths return a ``StdioCallResult`` — never raises.

        Parameters
        ----------
        tool:
            Tool name to call.
        call_args:
            Arguments dict passed as ``arguments`` in the JSON-RPC params.
            Never copied into error text.

        Returns
        -------
        StdioCallResult
            ``success=True, blocked=False`` on success.
            ``success=False, blocked=True`` when blocked by classification.
            ``success=False, blocked=False`` on transport failure.
        """
        args = call_args or {}
        classification = classify_with_schema(
            tool, self._schemas, server=self.server_name
        )

        if classification != "read":
            return self._blocked(
                tool,
                classification,
                f"MCP tool is not classified as read-only (classification: {classification})",
            )

        transport = call_stdio(
            self._argv,
            "tools/call",
            params={"name": tool, "arguments": args},
            timeout_seconds=self._timeout,
            max_output_bytes=self._max_output,
        )

        if not transport.success:
            warnings.warn(
                f"stdio MCP call failed for tool '{tool}': {transport.error}",
                RuntimeWarning,
                stacklevel=2,
            )
            return StdioCallResult(
                server=self.server_name,
                tool=tool,
                classification=classification,
                output="",
                error=transport.error,
                exit_code=transport.exit_code,
                success=False,
                blocked=False,
            )

        output = _extract_output(transport.result)
        return StdioCallResult(
            server=self.server_name,
            tool=tool,
            classification=classification,
            output=output,
            error="",
            exit_code=transport.exit_code,
            success=True,
            blocked=False,
        )

    def _blocked(
        self, tool: str, classification: str, reason: str
    ) -> StdioCallResult:
        warnings.warn(
            f"stdio MCP call blocked for tool '{tool}': {reason}",
            RuntimeWarning,
            stacklevel=3,
        )
        return StdioCallResult(
            server=self.server_name,
            tool=tool,
            classification=classification,
            output="",
            error=reason,
            exit_code=126,
            success=False,
            blocked=True,
        )


def _extract_output(result: Any) -> str:
    """Extract human-readable text from a tools/call result payload.

    Handles MCP content-block format (``{"content": [{"type": "text", ...}]}``)
    and falls back to JSON serialisation.  Never raises; returns empty string
    on extraction failure.
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    try:
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
