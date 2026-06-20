"""Approval binding integrity tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from safecode.enterprise.approvals.binding import workflow_approval_binding
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.state import Proposal
from safecode.enterprise.workflow.types import TaskType


def _proposal_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pr_live_binding_includes_proposal_sha256(tmp_path: Path) -> None:
    comment_path = tmp_path / "comment.md"
    comment_path.write_text("LGTM with notes\n", encoding="utf-8")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-binding0001",
        extra={"owner": "acme", "repo": "app", "pr_number": "42"},
    )
    state = state.model_copy(
        update={
            "request": state.request.model_copy(update={"input_kind": "pr_live"}),
            "proposals": [
                Proposal(
                    proposal_id="prop-comment-1",
                    kind="comment",
                    summary="review comment",
                    ref=str(comment_path),
                )
            ],
        }
    )
    _action, target = workflow_approval_binding(state)
    assert target["proposal_sha256"] == _proposal_digest(comment_path)
    assert target["owner"] == "acme"
    assert target["repo"] == "app"
    assert target["pr_number"] == "42"


def test_jira_binding_includes_proposal_sha256(tmp_path: Path) -> None:
    ticket_path = tmp_path / "ticket.md"
    ticket_path.write_text("Remediation plan\n", encoding="utf-8")
    state = build_initial_state(
        task_type=TaskType.secure_planning,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-binding0002",
        extra={"post_to_ticket": "1", "issue_key": "SEC-101"},
    )
    state = state.model_copy(
        update={
            "proposals": [
                Proposal(
                    proposal_id="prop-ticket-1",
                    kind="ticket",
                    summary="ticket comment",
                    ref=str(ticket_path),
                )
            ],
        }
    )
    _action, target = workflow_approval_binding(state)
    assert target["proposal_sha256"] == _proposal_digest(ticket_path)
    assert target["issue_key"] == "SEC-101"
