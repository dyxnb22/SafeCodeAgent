"""finalize node."""

from __future__ import annotations

from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.binding import workflow_approval_binding
from safecode.enterprise.approvals.store import consume_approved_request
from safecode.enterprise.connectors.github_pr_write import PRCommentWriteSpec, post_pr_comment
from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.render_pr_report import render_pr_report
from safecode.enterprise.workflow.render_remediation_report import render_remediation_report
from safecode.enterprise.workflow.remediation_patch import (
    apply_with_checkpoint,
    file_sha256,
    load_patch_proposal,
    rollback_last,
)
from safecode.enterprise.workflow.state import EnterpriseRunState, Report
from safecode.enterprise.workflow.tasks import remediation
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus

NODE_NAME = "finalize"


async def run(state: EnterpriseRunState) -> NodePatch:
    tool_calls = list(state.tool_calls)
    project_root = Path(state.repo.repo_root).resolve()
    sac_root = project_root / ".sac"

    def consume_required_approval() -> str:
        action, target = workflow_approval_binding(state)
        grant = consume_approved_request(
            sac_root,
            state.run_id,
            f"approval-{state.run_id}",
            tenant_id=state.tenant_id,
            action=action,
            policy_snapshot_id=state.policy_snapshot_id,
            target=target,
        )
        return grant.grant_id

    if state.task_type == TaskType.remediation:
        markdown = render_remediation_report(state)
        validation = state.validation
        patch_props = [item for item in state.proposals if item.kind == "patch"]
        final_status = WorkflowStatus.blocked if state.validation_failed else WorkflowStatus.succeeded
        if patch_props and not state.validation_failed:
            consume_required_approval()
            proposal = load_patch_proposal(Path(patch_props[0].ref))
            target = project_root / proposal.blocks[0].file_path
            before_hash = file_sha256(target) if target.is_file() else ""
            checkpoint_id = apply_with_checkpoint(project_root, proposal)
            post = remediation.run_post_apply_validation(
                state,
                finding=state.findings[0] if state.findings else None,
                regression=state.request.extra.get("post_validation_failed") == "1",
            )
            validation = post
            if not post.passed:
                rollback_last(project_root)
                final_status = WorkflowStatus.failed
                after = file_sha256(target) if target.is_file() else ""
                if before_hash and after != before_hash:
                    validation = validation.model_copy(
                        update={"details": {**validation.details, "rollback": "failed"}}
                    )
            else:
                validation = validation.model_copy(
                    update={"details": {**validation.details, "checkpoint_id": checkpoint_id}}
                )
        elif not state.validation_failed and state.risk_tier in {RiskTier.high, RiskTier.critical}:
            consume_required_approval()
        report = Report(
            report_id=f"report-{state.run_id}",
            kind="remediation_report",
            markdown=markdown,
        )
        return build_patch(
            state,
            NODE_NAME,
            summary="finalized remediation report",
            state_updates={
                "report": report,
                "validation": validation,
                "status": final_status,
                "tool_calls": tool_calls,
            },
        )

    if state.task_type == TaskType.pr_review:
        markdown = render_pr_report(state)
        report = Report(
            report_id=f"report-{state.run_id}",
            kind="pr_review_report",
            markdown=markdown,
        )
        if state.request.input_kind == "pr_live":
            comment_proposals = [item for item in state.proposals if item.kind == "comment"]
            if comment_proposals:
                consume_required_approval()
                body = Path(comment_proposals[0].ref).read_text(encoding="utf-8")
                record = post_pr_comment(
                    sac_root=sac_root,
                    run_id=state.run_id,
                    node_name=NODE_NAME,
                    spec=PRCommentWriteSpec(mode="live"),
                    body=body,
                    approved=True,
                    actor_id=state.actor_id,
                    tenant_id=state.tenant_id,
                    policy_snapshot_id=state.policy_snapshot_id,
                )
                tool_calls.append(record)
        elif state.risk_tier in {RiskTier.high, RiskTier.critical}:
            consume_required_approval()
        return build_patch(
            state,
            NODE_NAME,
            summary="finalized PR review report",
            state_updates={
                "report": report,
                "status": WorkflowStatus.succeeded,
                "tool_calls": tool_calls,
            },
        )

    markdown = redact_secrets(
        f"# Enterprise Workflow Report\n\nRun `{state.run_id}` completed for "
        f"{state.task_type.value}.\n"
    )
    report = Report(
        report_id=f"report-{state.run_id}",
        kind="pr_review_report",
        markdown=markdown,
    )
    return build_patch(
        state,
        NODE_NAME,
        summary="finalized redacted report",
        state_updates={"report": report, "status": WorkflowStatus.succeeded},
    )
