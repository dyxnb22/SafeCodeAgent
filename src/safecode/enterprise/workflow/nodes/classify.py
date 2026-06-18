"""classify_request node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import WorkflowStatus

NODE_NAME = "classify_request"


async def run(state: EnterpriseRunState) -> NodePatch:
    return build_patch(
        state,
        NODE_NAME,
        summary=f"classified task {state.task_type.value}",
        state_updates={
            "status": WorkflowStatus.running,
            "missing_evidence": False,
        },
    )
