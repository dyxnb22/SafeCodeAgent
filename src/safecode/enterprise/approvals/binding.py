"""Deterministic workflow action bindings for human approvals."""

from __future__ import annotations

import hashlib
from pathlib import Path

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.connectors.github_pr_write import comment_approval_target
from safecode.enterprise.connectors.jira_live import comment_approval_target as jira_comment_approval_target
from safecode.enterprise.workflow.state import EnterpriseRunState, Proposal
from safecode.enterprise.workflow.types import TaskType


def _proposal_digest(proposal: Proposal | None) -> str:
    if proposal is None:
        return ""
    path = Path(proposal.ref)
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow_approval_binding(state: EnterpriseRunState) -> tuple[Action, dict[str, str]]:
    """Bind approval to the exact proposal that finalize may execute."""
    proposal: Proposal | None = None
    if state.task_type == TaskType.remediation:
        action = Action.file_write
        proposal = next((item for item in state.proposals if item.kind == "patch"), None)
    elif state.task_type == TaskType.pr_review and state.request.input_kind == "pr_live":
        action = Action.github_write_comment
        proposal = next((item for item in state.proposals if item.kind == "comment"), None)
        if proposal is not None and proposal.ref:
            body = Path(proposal.ref).read_text(encoding="utf-8")
            owner = state.request.extra.get("owner", "")
            repo = state.request.extra.get("repo", "")
            try:
                pr_number = int(state.request.extra.get("pr_number") or 0)
            except ValueError:
                pr_number = 0
            if owner and repo and pr_number > 0:
                return action, comment_approval_target(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    body=body,
                )
    elif state.task_type == TaskType.secure_planning and state.request.extra.get("post_to_ticket") == "1":
        action = Action.issue_comment
        proposal = next((item for item in state.proposals if item.kind == "ticket"), None)
        if proposal is not None and proposal.ref:
            body = Path(proposal.ref).read_text(encoding="utf-8")
            issue_key = state.request.extra.get("issue_key", "")
            if issue_key:
                return action, jira_comment_approval_target(issue_key=issue_key, body=body)
    else:
        action = Action.file_write
        proposal = next(iter(state.proposals), None)
    return action, {
        "proposal_id": proposal.proposal_id if proposal else "",
        "proposal_ref": proposal.ref if proposal else "",
        "proposal_sha256": _proposal_digest(proposal),
    }
