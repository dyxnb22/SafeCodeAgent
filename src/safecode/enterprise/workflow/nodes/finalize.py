"""finalize node."""

from __future__ import annotations

from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.store import list_requests
from safecode.enterprise.connectors.github_pr_write import PRCommentWriteSpec, post_pr_comment
from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.render_pr_report import render_pr_report
from safecode.enterprise.workflow.state import EnterpriseRunState, Report
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

NODE_NAME = "finalize"


async def run(state: EnterpriseRunState) -> NodePatch:
    tool_calls = list(state.tool_calls)
    if state.task_type == TaskType.pr_review:
        markdown = render_pr_report(state)
        report = Report(
            report_id=f"report-{state.run_id}",
            kind="pr_review_report",
            markdown=markdown,
        )
        if state.request.input_kind == "pr_live":
            approved = any(item.status == "approved" for item in list_requests(
                Path(state.repo.repo_root) / ".sac",
                state.run_id,
            ))
            comment_proposals = [item for item in state.proposals if item.kind == "comment"]
            if comment_proposals:
                body = Path(comment_proposals[0].ref).read_text(encoding="utf-8")
                record = post_pr_comment(
                    sac_root=Path(state.repo.repo_root) / ".sac",
                    run_id=state.run_id,
                    node_name=NODE_NAME,
                    spec=PRCommentWriteSpec(mode="live"),
                    body=body,
                    approved=approved,
                    actor_id=state.actor_id,
                )
                tool_calls.append(record)
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
