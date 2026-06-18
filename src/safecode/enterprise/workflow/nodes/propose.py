"""propose_report_or_patch node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, Proposal

NODE_NAME = "propose_report_or_patch"


async def run(state: EnterpriseRunState) -> NodePatch:
    proposal = Proposal(
        proposal_id=f"proposal-{state.run_id}",
        kind="report",
        summary="proposed local report draft",
        ref=f".sac/enterprise/runs/{state.run_id}/proposal.md",
    )
    return build_patch(
        state,
        NODE_NAME,
        summary="proposed report draft",
        state_updates={"proposals": [proposal]},
    )
