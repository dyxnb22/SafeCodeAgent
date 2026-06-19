"""finalize node."""

from __future__ import annotations

from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.binding import workflow_approval_binding
from safecode.enterprise.connectors.github_pr_write import PRCommentWriteSpec, post_pr_comment
from safecode.enterprise.connectors.jira_live import IssueCommentWriteSpec, post_issue_comment
from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.render_planning_report import render_planning_report
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
    run_dir = sac_root / "enterprise" / "runs" / state.run_id

    def consume_required_approval() -> str:
        from safecode.enterprise.persistence.local_backend import LocalBackend

        action, target = workflow_approval_binding(state)
        backend = LocalBackend(sac_root)
        grant = backend.approvals.consume_approved_request(
            tenant_id=state.tenant_id,
            run_id=state.run_id,
            request_id=f"approval-{state.run_id}",
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
                body = Path(comment_proposals[0].ref).read_text(encoding="utf-8")
                owner = state.request.extra.get("owner")
                repo = state.request.extra.get("repo")
                pr_number_raw = state.request.extra.get("pr_number")
                pr_number = int(pr_number_raw) if pr_number_raw and pr_number_raw.isdigit() else None
                from safecode.enterprise.connectors.session import (
                    get_github_access_token,
                    get_github_transport,
                )

                access_token = get_github_access_token()
                transport = get_github_transport()
                governed_write = (
                    access_token is not None
                    and owner
                    and repo
                    and pr_number is not None
                    and pr_number > 0
                )
                record = post_pr_comment(
                    sac_root=sac_root,
                    run_id=state.run_id,
                    node_name=NODE_NAME,
                    spec=PRCommentWriteSpec(
                        mode="live",
                        owner=owner,
                        repo=repo,
                        pr_number=pr_number,
                    ),
                    body=body,
                    approved=not governed_write,
                    actor_id=state.actor_id,
                    tenant_id=state.tenant_id,
                    policy_snapshot_id=state.policy_snapshot_id,
                    request_id=f"approval-{state.run_id}" if governed_write else None,
                    access_token=access_token,
                    transport=transport,
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

    if state.task_type == TaskType.secure_planning:
        markdown = render_planning_report(state)
        report = Report(
            report_id=f"report-{state.run_id}",
            kind="plan_report",
            markdown=markdown,
        )
        if state.request.extra.get("post_to_ticket") == "1":
            ticket_proposals = [item for item in state.proposals if item.kind == "ticket"]
            if ticket_proposals:
                body = Path(ticket_proposals[0].ref).read_text(encoding="utf-8")
                issue_key = state.request.extra.get("issue_key", "")
                base_url = state.request.extra.get("jira_base_url", "https://example.atlassian.net")
                from safecode.enterprise.connectors.session import (
                    get_jira_api_token,
                    get_jira_email,
                    get_jira_transport,
                )

                email = get_jira_email()
                api_token = get_jira_api_token()
                transport = get_jira_transport()
                governed_write = email is not None and api_token is not None and bool(issue_key)
                record = post_issue_comment(
                    sac_root=sac_root,
                    run_id=state.run_id,
                    node_name=NODE_NAME,
                    spec=IssueCommentWriteSpec(
                        mode="live" if governed_write else "fixture",
                        issue_key=issue_key or None,
                        api_base_url=base_url,
                        output_path=str(run_dir / "posted_ticket_comment.md") if not governed_write else None,
                    ),
                    body=body,
                    approved=not governed_write,
                    actor_id=state.actor_id,
                    tenant_id=state.tenant_id,
                    policy_snapshot_id=state.policy_snapshot_id,
                    request_id=f"approval-{state.run_id}" if governed_write else None,
                    email=email,
                    api_token=api_token,
                    transport=transport,
                )
                tool_calls.append(record)
        return build_patch(
            state,
            NODE_NAME,
            summary="finalized secure planning report",
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
