"""Model tool call adapter — validate LLM intents against ToolRegistry (v2.2.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from safecode.tools.registry import (
    AuditEventRef,
    PermissionCategory,
    ToolRegistry,
    ToolRiskLevel,
    ToolSpec,
)


class AdapterError(ValueError):
    """Raised when tool call validation fails (unknown tool, bad args, type mismatch)."""


class ToolCallValidationResult(BaseModel):
    """Validated tool call with registry metadata attached, ready for routing."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    spec: ToolSpec
    resolved_args: dict[str, Any]
    requires_approval: bool
    risk: ToolRiskLevel
    permission_category: PermissionCategory
    audit_event: AuditEventRef | None


_ARG_TYPE_CHECKS: dict[str, type] = {
    "str": str,
    "int": int,
    "bool": bool,
    "path": str,
    "dict": dict,
    "list": list,
}


class ToolCallAdapter:
    """Validate a structured LLM tool intent against the ToolRegistry before routing.

    Fails closed: unknown tools, missing required arguments, and type mismatches
    all raise AdapterError. No tool execution or network access occurs.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or ToolRegistry()

    def validate(self, tool_name: str, args: dict[str, Any]) -> ToolCallValidationResult:
        """Validate tool_name and args against the registry; return typed metadata or raise.

        Raises:
            AdapterError: for unknown tool names, missing required args, or type mismatches.
        """
        spec = self.lookup(tool_name)
        self._check_required_args(spec, args, tool_name)
        self._check_arg_types(spec, args, tool_name)
        return ToolCallValidationResult(
            tool_name=tool_name,
            spec=spec,
            resolved_args=dict(args),
            requires_approval=spec.requires_human_approval,
            risk=spec.risk,
            permission_category=spec.permission_category,
            audit_event=spec.audit_event,
        )

    def lookup(self, tool_name: str) -> ToolSpec:
        """Return the ToolSpec for tool_name or raise AdapterError for unknown names."""
        try:
            return self._registry.get(tool_name)
        except KeyError:
            raise AdapterError(f"Unknown tool: {tool_name!r}") from None

    def _check_required_args(
        self, spec: ToolSpec, args: dict[str, Any], tool_name: str
    ) -> None:
        for arg_schema in spec.args:
            if arg_schema.required and arg_schema.name not in args:
                raise AdapterError(
                    f"Missing required argument {arg_schema.name!r} for tool {tool_name!r}"
                )

    def _check_arg_types(
        self, spec: ToolSpec, args: dict[str, Any], tool_name: str
    ) -> None:
        schema_by_name = {a.name: a for a in spec.args}
        for arg_name, arg_value in args.items():
            arg_schema = schema_by_name.get(arg_name)
            if arg_schema is None:
                continue
            expected = _ARG_TYPE_CHECKS.get(arg_schema.type)
            if expected is not None and not isinstance(arg_value, expected):
                raise AdapterError(
                    f"Argument {arg_name!r} for tool {tool_name!r}: "
                    f"expected {arg_schema.type}, got {type(arg_value).__name__}"
                )
