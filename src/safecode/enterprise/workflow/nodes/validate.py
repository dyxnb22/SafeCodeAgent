"""validate node."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, ValidationResult
from safecode.enterprise.workflow.tasks import remediation, secure_planning

NODE_NAME = "validate"


async def run(state: EnterpriseRunState) -> NodePatch:
    if secure_planning.is_secure_planning_task(state):
        validation = ValidationResult(
            passed=True,
            summary="validation skipped for secure_planning workflow",
            details={"skipped": "secure_planning does not run scanners"},
        )
        return build_patch(
            state,
            NODE_NAME,
            summary=validation.summary,
            state_updates={"validation": validation, "validation_failed": False},
        )
    if remediation.is_remediation_task(state):
        validation = remediation.run_pre_apply_validation(state)
        return build_patch(
            state,
            NODE_NAME,
            summary=validation.summary,
            state_updates={
                "validation": validation,
                "validation_failed": not validation.passed,
            },
            status="soft_failure" if not validation.passed else "ok",
        )
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
