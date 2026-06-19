"""collect_repo_context node."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning

NODE_NAME = "collect_repo_context"


async def run(state: EnterpriseRunState) -> NodePatch:
    updates: dict = {"missing_evidence": False}
    repo_root = Path(state.repo.repo_root).resolve()
    if remediation.is_remediation_task(state) and state.request.input_kind in {
        "finding_fixture",
        "finding_live",
    }:
        try:
            findings = remediation.ingest_findings(repo_root, state.request.input_ref)
        except Exception:
            findings = []
        if not findings:
            updates["missing_evidence"] = True
        else:
            updates["findings"] = findings
    elif pr_review.is_pr_review_task(state) and state.request.input_kind in {
        "pr_fixture",
        "pr_live",
    }:
        evidence = pr_review.collect_pull_request(
            repo_root,
            state.request.input_ref,
            input_kind=state.request.input_kind,
            extra=state.request.extra,
            installation_id=state.request.extra.get("installation_id"),
        )
        if evidence is None or not evidence.hunks:
            updates["missing_evidence"] = True
        else:
            updates["pull_request_evidence"] = evidence
    elif secure_planning.is_secure_planning_task(state) and state.request.input_kind == "ticket":
        evidence, issue_key = secure_planning.collect_issue(
            repo_root,
            state.request.input_ref,
            input_kind=state.request.input_kind,
            extra=state.request.extra,
        )
        if evidence is None:
            updates["missing_evidence"] = True
        else:
            updates["issue_evidence"] = evidence
            if issue_key and state.request.extra.get("issue_key") is None:
                updates["request"] = state.request.model_copy(
                    update={"extra": {**state.request.extra, "issue_key": issue_key}}
                )
    return build_patch(
        state,
        NODE_NAME,
        summary="collected repository context",
        state_updates=updates,
    )
