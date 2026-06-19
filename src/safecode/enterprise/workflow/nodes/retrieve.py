"""retrieve_policy_and_code node."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning

NODE_NAME = "retrieve_policy_and_code"


async def run(state: EnterpriseRunState) -> NodePatch:
    updates: dict = {}
    if remediation.is_remediation_task(state) and state.findings:
        citations = remediation.retrieve_citations(state, state.findings)
        updates["citations"] = citations
        updates["missing_evidence"] = len(citations) == 0
    elif pr_review.is_pr_review_task(state) and state.pull_request_evidence is not None:
        citations = pr_review.retrieve_citations(state, state.pull_request_evidence)
        updates["citations"] = citations
        updates["missing_evidence"] = len(citations) == 0
    elif secure_planning.is_secure_planning_task(state) and state.issue_evidence is not None:
        citations = secure_planning.retrieve_citations(state, state.issue_evidence)
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
