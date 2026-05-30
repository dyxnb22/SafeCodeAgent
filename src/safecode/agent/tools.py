"""Typed tool intents for the interactive agent loop."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


ToolIntentType = Literal["read", "patch", "shell", "sandbox", "mcp", "subagent", "report"]


class ToolIntent(BaseModel):
    """A model- or runtime-proposed tool action before execution."""

    type: ToolIntentType
    description: str = ""
    target: str | None = None
    command: str | None = None
    tool_name: str | None = None
    input_json: dict | None = None
    task_id: str | None = None
    requires_approval: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ToolIntent":
        if self.type in {"read", "patch", "report"} and not self.target:
            raise ValueError(f"{self.type} intent requires target")
        if self.type in {"shell", "sandbox"} and not self.command:
            raise ValueError(f"{self.type} intent requires command")
        if self.type == "mcp" and not self.tool_name:
            raise ValueError("mcp intent requires tool_name")
        if self.type == "subagent" and not self.task_id:
            raise ValueError("subagent intent requires task_id")
        return self


class RoutedToolIntent(BaseModel):
    """Validated route decision for a tool intent."""

    intent: ToolIntent
    route: str
    executable_now: bool
    reason: str


class ToolIntentRouter:
    """Validate and route tool intents without executing them."""

    ROUTES = {
        "read": "context.read",
        "patch": "patch.propose",
        "shell": "shell.propose",
        "sandbox": "sandbox.propose",
        "mcp": "mcp.propose",
        "subagent": "subagent.inspect",
        "report": "report.render",
    }
    APPROVAL_REQUIRED = {"patch", "shell", "sandbox", "mcp"}

    def route(self, raw_intent: dict) -> RoutedToolIntent:
        """Return a route decision for a raw intent dict."""
        try:
            intent = ToolIntent(**raw_intent)
        except (TypeError, ValidationError, ValueError) as exc:
            raise ValueError(f"Invalid tool intent: {exc}") from exc

        approval_required = intent.type in self.APPROVAL_REQUIRED or intent.requires_approval
        normalized = intent.model_copy(update={"requires_approval": approval_required})
        route = self.ROUTES[normalized.type]
        return RoutedToolIntent(
            intent=normalized,
            route=route,
            executable_now=not approval_required,
            reason="approval_required" if approval_required else "safe_to_route",
        )
