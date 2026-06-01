"""Universal tool call gate — pre-flight check for write/execute/dispatch paths (v2.3.7).

Every CLI and agent-loop path that can write, execute, apply, dispatch, or communicate
with tools must pass this gate *before* performing side effects.  Fails closed:
unknown tool names, missing required args, invalid arg types, and unapproved
approval-required tools are all blocked here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from safecode.tools.adapter import AdapterError, ToolCallAdapter, ToolCallValidationResult
from safecode.tools.registry import ToolRegistry


@dataclass(frozen=True)
class GateResult:
    """Outcome of a ToolCallGate check."""

    allowed: bool
    reason: str
    validation: ToolCallValidationResult | None = None


class GateError(ValueError):
    """Raised by ToolCallGate.must_pass() / must_pass_intent() when the gate blocks."""


class ToolCallGate:
    """Pre-flight gate that wraps ToolCallAdapter.

    Fail-closed contract:
    - Unknown tool name                         → blocked
    - Missing required arg                      → blocked
    - Wrong arg type                            → blocked
    - requires_human_approval=True, approved=False → blocked

    No tool is executed or any file written by this class.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._adapter = ToolCallAdapter(registry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self, tool_name: str, args: dict[str, Any], *, approved: bool = False
    ) -> GateResult:
        """Full gate check: validates name, required args, arg types, and approval.

        Args:
            tool_name: Registered tool name (e.g. ``"patch.apply"``).
            args:      Dict of arguments as they would be passed to the tool.
            approved:  True if the caller has already obtained human approval for
                       this specific invocation (e.g. after typer.confirm).

        Returns a :class:`GateResult` with ``allowed=False`` to block; callers must
        inspect ``allowed`` before proceeding.
        """
        try:
            validation = self._adapter.validate(tool_name, args)
        except AdapterError as exc:
            return GateResult(allowed=False, reason=str(exc))

        if validation.requires_approval and not approved:
            return GateResult(
                allowed=False,
                reason=f"Tool {tool_name!r} requires human approval before execution.",
                validation=validation,
            )

        return GateResult(allowed=True, reason="ok", validation=validation)

    def check_intent(
        self, tool_name: str, *, approved: bool = False
    ) -> GateResult:
        """Intent-level gate: validates name and approval state only (no arg validation).

        Use when the full argument dict is not yet available at the call site
        (e.g. the LLM will generate them later, or the CLI accepts a free-form task
        string rather than structured tool args).
        """
        try:
            spec = self._adapter.lookup(tool_name)
        except AdapterError as exc:
            return GateResult(allowed=False, reason=str(exc))

        validation = ToolCallValidationResult(
            tool_name=tool_name,
            spec=spec,
            resolved_args={},
            requires_approval=spec.requires_human_approval,
            risk=spec.risk,
            permission_category=spec.permission_category,
            audit_event=spec.audit_event,
        )

        if validation.requires_approval and not approved:
            return GateResult(
                allowed=False,
                reason=f"Tool {tool_name!r} requires human approval before execution.",
                validation=validation,
            )

        return GateResult(allowed=True, reason="ok", validation=validation)

    def must_pass(
        self, tool_name: str, args: dict[str, Any], *, approved: bool = False
    ) -> ToolCallValidationResult:
        """Like :meth:`check` but raises :class:`GateError` instead of returning blocked."""
        result = self.check(tool_name, args, approved=approved)
        if not result.allowed:
            raise GateError(result.reason)
        assert result.validation is not None  # always set when allowed
        return result.validation

    def must_pass_intent(
        self, tool_name: str, *, approved: bool = False
    ) -> ToolCallValidationResult:
        """Like :meth:`check_intent` but raises :class:`GateError` instead of returning blocked."""
        result = self.check_intent(tool_name, approved=approved)
        if not result.allowed:
            raise GateError(result.reason)
        assert result.validation is not None
        return result.validation
