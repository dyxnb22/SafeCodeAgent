"""collect_context PR wiring tests (v1.3.2-T3)."""

import asyncio
import json
from pathlib import Path

from safecode.enterprise.workflow.nodes.collect_context import run as collect_run
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType


def test_collect_context_attaches_pr_evidence(tmp_path: Path):
    fixture = tmp_path / "pr.json"
    fixture.write_text(
        json.dumps(
            {
                "title": "Security fix",
                "body": "Fix issue",
                "author": "dev@example.com",
                "base_ref": "main",
                "head_ref": "feature/x",
                "files": [],
                "hunks": [],
            }
        ),
        encoding="utf-8",
    )
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=str(fixture.name),
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-prctx0001",
        extra={},
    )
    state = state.model_copy(
        update={
            "request": state.request.model_copy(update={"input_kind": "pr_fixture"}),
        }
    )
    patch = asyncio.run(collect_run(state))
    assert patch.state_updates["pull_request_evidence"].title == "Security fix"
    assert patch.state_updates["missing_evidence"] is False


def test_collect_context_marks_missing_pr_fixture_as_missing_evidence(
    tmp_path: Path,
):
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="missing-pr.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-prctx0002",
        extra={},
    )
    state = state.model_copy(
        update={
            "request": state.request.model_copy(update={"input_kind": "pr_fixture"}),
        }
    )

    patch = asyncio.run(collect_run(state))

    assert patch.state_updates["missing_evidence"] is True
    assert "pull_request_evidence" not in patch.state_updates
