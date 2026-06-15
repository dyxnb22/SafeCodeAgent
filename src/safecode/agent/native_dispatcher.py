"""NativeToolDispatcher: routes native tool calls to registered handlers (v4.20+)."""

from __future__ import annotations

from typing import Any, Callable

from safecode.agent.native_tools import NativeToolCall, NativeToolResult, NativeToolSpec


Handler = Callable[[str, dict[str, Any]], NativeToolResult]


class NativeToolDispatcher:
    """Registry and dispatcher for native tool calls."""

    def __init__(self) -> None:
        self._specs: dict[str, NativeToolSpec] = {}
        self._handlers: dict[str, Handler] = {}

    def register(self, spec: NativeToolSpec, handler: Handler) -> None:
        """Register a tool spec and its handler."""
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def specs(self) -> list[NativeToolSpec]:
        """Return all registered specs sorted by name."""
        return sorted(self._specs.values(), key=lambda s: s.name)

    def get_spec(self, tool_name: str) -> NativeToolSpec | None:
        return self._specs.get(tool_name)

    def dispatch(self, call: NativeToolCall) -> NativeToolResult:
        """Dispatch a tool call. Unknown tools return error result."""
        handler = self._handlers.get(call.tool_name)
        if handler is None:
            return NativeToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status="error",
                error=f"Unknown tool: {call.tool_name!r}",
            )
        try:
            return handler(call.call_id, call.input)
        except Exception as exc:
            return NativeToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status="error",
                error=f"Tool execution error: {type(exc).__name__}",
            )

    def system_prompt_section(self) -> str:
        """Render an ## Available Tools section for the agent system prompt."""
        if not self._specs:
            return ""
        lines = ["## Available Tools", ""]
        for spec in self.specs():
            lines.append(f"### {spec.name}")
            lines.append(spec.description)
            if spec.requires_approval:
                lines.append("_Requires approval before execution._")
            if spec.input_schema:
                import json
                lines.append(f"Input schema: `{json.dumps(spec.input_schema)}`")
            lines.append("")
        return "\n".join(lines)
