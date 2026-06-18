"""collect_repo_context node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState

NODE_NAME = "collect_repo_context"


async def run(state: EnterpriseRunState) -> NodePatch:
    return build_patch(
        state,
        NODE_NAME,
        summary="collected repository context",
        state_updates={"missing_evidence": False},
    )
