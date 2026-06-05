"""EXPERIMENTAL: Typed step model for the agent loop (v4.11.0+).

These are typed projections over the existing AgentStepResult / AgentRunResult
dataclasses. The legacy return types are preserved for backward compatibility;
this module adds classification metadata without altering any existing contracts.

All surfaces in this module are EXPERIMENTAL and carry no stable contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from safecode.utils.time import utc_now_iso


AgentStepKind = Literal[
    "plan",
    "ask",
    "edit",
    "apply",
    "run",
    "fix",
    "commit",
    "rollback",
    "mcp_call",
    "subagent_dispatch",
    "stop",
]

AgentStepStatus = Literal[
    "success",
    "blocked",
    "approved",
    "rejected",
    "failed",
    "interrupted",
    "waiting_for_user",
]

# Kinds that unconditionally require explicit interactive approval before
# any mutating execution.  This set is authoritative; tests enforce it.
APPROVAL_REQUIRED_KINDS: frozenset[AgentStepKind] = frozenset(
    {"edit", "apply", "run", "fix", "commit", "rollback"}
)

# Kinds that are safe to auto-approve when --auto-approve-read-only is active.
READ_ONLY_AUTO_APPROVABLE_KINDS: frozenset[AgentStepKind] = frozenset({"ask"})


class TypedAgentStep(BaseModel):
    """Typed projection of one agent step decision.

    Created alongside each AgentStepResult to carry kind/status metadata
    for the journal (v4.11.1) and validation loop (v4.11.3+).
    """

    index: int
    kind: AgentStepKind
    description: str = ""
    requires_approval: bool
    created_at: str = Field(default_factory=utc_now_iso)
    payload_version: int = 1

    @classmethod
    def from_route(
        cls,
        index: int,
        kind: AgentStepKind,
        description: str = "",
    ) -> "TypedAgentStep":
        """Construct a TypedAgentStep, deriving requires_approval from the kind."""
        return cls(
            index=index,
            kind=kind,
            description=description,
            requires_approval=kind in APPROVAL_REQUIRED_KINDS,
        )


class TypedAgentStepResult(BaseModel):
    """Typed projection of the outcome of one agent step.

    Created alongside each AgentStepResult to carry classification
    metadata for the journal and validation loop.
    """

    step_index: int
    kind: AgentStepKind
    status: AgentStepStatus
    summary: str = ""
    audit_trace_id: str | None = None
    pending_patch_id: str | None = None
    failure_category: str | None = None
    payload_version: int = 1


def classify_step_from_pending_action(
    step_index: int,
    pending_action: dict[str, object] | None,
    observation: str,
    stopped_for_approval: bool,
    *,
    failure_category: str | None = None,
) -> tuple[TypedAgentStep, TypedAgentStepResult]:
    """Classify a completed step into typed step + result.

    Derives kind from the pending_action dict shape that AgentLoop already
    produces; falls back to ``"ask"`` for ambiguous/missing actions.
    This is a pure classifier — it never executes any action.
    """
    action = pending_action or {}
    action_type = str(action.get("type", ""))
    route = str(action.get("route", ""))

    kind = _classify_kind(action_type, route, failure_category)
    status = _classify_status(kind, stopped_for_approval, failure_category, action)

    patch_id = str(action.get("patch_id", "")) or None

    step = TypedAgentStep.from_route(index=step_index, kind=kind, description=observation[:200])
    result = TypedAgentStepResult(
        step_index=step_index,
        kind=kind,
        status=status,
        summary=observation[:500],
        pending_patch_id=patch_id,
        failure_category=failure_category,
    )
    return step, result


def _classify_kind(
    action_type: str, route: str, failure_category: str | None
) -> AgentStepKind:
    if failure_category == "model_output_invalid":
        return "ask"

    if action_type == "stop_for_user":
        return "stop"

    if action_type == "patch" or route in ("patch.propose", "patch.apply"):
        return "edit"

    if action_type == "mcp":
        if route == "mcp.execute_approved_write":
            return "apply"
        return "mcp_call"

    if action_type == "subagent":
        return "subagent_dispatch"

    return "ask"


def _classify_status(
    kind: AgentStepKind,
    stopped_for_approval: bool,
    failure_category: str | None,
    action: dict[str, object],
) -> AgentStepStatus:
    if failure_category:
        return "failed"

    if kind == "stop":
        return "waiting_for_user"

    if stopped_for_approval:
        return "waiting_for_user"

    if kind in APPROVAL_REQUIRED_KINDS:
        return "approved"

    return "success"
