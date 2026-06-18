"""retrieve_policy_and_code node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState

NODE_NAME = "retrieve_policy_and_code"


async def run(state: EnterpriseRunState) -> NodePatch:
    missing = len(state.citations) == 0
    return build_patch(
        state,
        NODE_NAME,
        summary="retrieved policy and code citations",
        state_updates={"missing_evidence": missing},
    )
