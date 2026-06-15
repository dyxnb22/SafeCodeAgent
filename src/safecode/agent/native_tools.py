"""Native tool protocol definitions for SafeCode Agent (experimental, v4.20+).

Wire format sent by the model:
  {"type": "native_tool_call", "tool_name": "read_file", "input": {...}}

The existing ToolIntentRouter is untouched; both protocols coexist.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NativeToolSpec(BaseModel):
    """Schema a tool exposes to the model (and to Typer help)."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    audit_event_type: str = "tool_call_read"
    experimental: bool = True


class NativeToolCall(BaseModel):
    """A tool call emitted by the model."""

    type: Literal["native_tool_call"] = "native_tool_call"
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    call_id: str = ""


class NativeToolResult(BaseModel):
    """Structured response returned to the model after tool execution."""

    call_id: str
    tool_name: str
    status: Literal["success", "blocked", "error"] = "success"
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_context_block(self) -> str:
        """Render as a compact context block for the model."""
        if self.status == "success":
            return f"[tool:{self.tool_name}]\n{self.output or ''}"
        return f"[tool:{self.tool_name}] {self.status}: {self.error or 'unknown error'}"
