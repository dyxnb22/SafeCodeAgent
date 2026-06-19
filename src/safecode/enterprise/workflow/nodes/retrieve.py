"""retrieve_policy_and_code node."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review

NODE_NAME = "retrieve_policy_and_code"


async def run(state: EnterpriseRunState) -> NodePatch:
    updates: dict = {}
    if pr_review.is_pr_review_task(state) and state.pull_request_evidence is not None:
        citations = pr_review.retrieve_citations(state, state.pull_request_evidence)
        updates["citations"] = citations
        updates["missing_evidence"] = len(citations) == 0
    else:
        missing = len(state.citations) == 0
        updates["missing_evidence"] = missing
    return build_patch(
        state,
        NODE_NAME,
        summary="retrieved policy and code citations",
        state_updates=updates,
    )
