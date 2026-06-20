"""Apply immutable node patches to workflow state."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.exceptions import InvalidStateUpdateError
from safecode.enterprise.workflow.state import EnterpriseRunState

_IMMUTABLE_STATE_FIELDS = frozenset({
    "schema_version",
    "actor_id",
    "tenant_id",
    "run_id",
    "task_type",
    "policy_snapshot_id",
    "subject",
    "repo",
    "created_at",
})


def apply_patch(state: EnterpriseRunState, patch: NodePatch) -> EnterpriseRunState:
    """Return a new state with validated updates from a node patch."""
    merged = state.model_dump(mode="python")
    allowed = set(EnterpriseRunState.model_fields)
    for key, value in patch.state_updates.items():
        if key not in allowed:
            raise InvalidStateUpdateError(f"unknown state key: {key}")
        if key in _IMMUTABLE_STATE_FIELDS:
            raise InvalidStateUpdateError(f"node patch may not overwrite immutable field: {key!r}")
        if key == "request":
            request = state.request.model_validate(value)
            expected_identity = (state.request.task_type, state.request.input_ref, state.actor_id)
            actual_identity = (request.task_type, request.input_ref, request.actor_id)
            if actual_identity != expected_identity:
                raise InvalidStateUpdateError("node patch may not overwrite request identity")
        merged[key] = value
    return EnterpriseRunState.model_validate(merged)
