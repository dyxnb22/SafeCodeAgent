"""validate node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, ValidationResult

NODE_NAME = "validate"


async def run(state: EnterpriseRunState) -> NodePatch:
    failed = state.request.extra.get("validation_failed") == "1"
    validation = ValidationResult(
        passed=not failed,
        summary="validation failed" if failed else "validation passed",
    )
    return build_patch(
        state,
        NODE_NAME,
        summary=validation.summary,
        state_updates={"validation": validation, "validation_failed": failed},
        status="soft_failure" if failed else "ok",
    )
