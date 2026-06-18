"""Apply immutable node patches to workflow state."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.exceptions import InvalidStateUpdateError
from safecode.enterprise.workflow.state import EnterpriseRunState


def apply_patch(state: EnterpriseRunState, patch: NodePatch) -> EnterpriseRunState:
    """Return a new state with validated updates from a node patch."""
    merged = state.model_dump(mode="python")
    allowed = set(EnterpriseRunState.model_fields)
    for key, value in patch.state_updates.items():
        if key not in allowed:
            raise InvalidStateUpdateError(f"unknown state key: {key}")
        merged[key] = value
    return EnterpriseRunState.model_validate(merged)
