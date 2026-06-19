"""propose_report_or_patch node."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.render_pr_report import render_pr_report
from safecode.enterprise.workflow.render_remediation_report import render_remediation_report
from safecode.enterprise.workflow.remediation_patch import write_patch_proposal
from safecode.enterprise.workflow.state import EnterpriseRunState, Proposal
from safecode.enterprise.workflow.tasks import pr_review, remediation

NODE_NAME = "propose_report_or_patch"


async def run(state: EnterpriseRunState) -> NodePatch:
    run_dir = Path(state.repo.repo_root) / ".sac" / "enterprise" / "runs" / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if remediation.is_remediation_task(state) and state.findings:
        report_path = run_dir / "report.md"
        report_path.write_text(render_remediation_report(state), encoding="utf-8")
        patch_proposal = remediation.build_patch_proposal(state, state.findings[0])
        patch_ref = None
        proposals = remediation.build_proposals(
            state,
            report_ref=str(report_path),
            patch_ref=None,
            patch_proposal=None,
        )
        if patch_proposal is not None:
            patch_path = write_patch_proposal(run_dir, patch_proposal)
            patch_ref = str(patch_path)
            proposals = remediation.build_proposals(
                state,
                report_ref=str(report_path),
                patch_ref=patch_ref,
                patch_proposal=patch_proposal,
            )
        return build_patch(
            state,
            NODE_NAME,
            summary="proposed remediation artifacts",
            state_updates={"proposals": proposals},
        )

    if pr_review.is_pr_review_task(state):
        report_path = run_dir / "report.md"
        report_path.write_text(render_pr_report(state), encoding="utf-8")
        comment_ref: str | None = None
        proposals = pr_review.build_pr_proposals(
            state,
            report_ref=str(report_path),
            comment_ref=None,
        )
        if state.findings:
            comment_path = run_dir / "draft_comment.md"
            comment_path.write_text(
                pr_review.build_comment_body(state.findings, state.risk_tier or state.findings[0].severity),
                encoding="utf-8",
            )
            comment_ref = str(comment_path)
            proposals = pr_review.build_pr_proposals(
                state,
                report_ref=str(report_path),
                comment_ref=comment_ref,
            )
        return build_patch(
            state,
            NODE_NAME,
            summary="proposed PR review artifacts",
            state_updates={"proposals": proposals},
        )

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
