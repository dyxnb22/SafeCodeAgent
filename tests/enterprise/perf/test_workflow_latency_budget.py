"""Workflow latency budget tests."""

import asyncio
import time
from pathlib import Path

from safecode.enterprise.perf.budgets import WORKFLOW_LATENCY_BUDGET_MS, check_workflow_budget
from safecode.enterprise.trace.timeline import build_timeline
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = _ROOT / "examples" / "enterprise" / "fixtures" / "pr_benign"


def test_pr_review_fixture_finishes_within_latency_budget(tmp_path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=str(_FIXTURE),
        actor_id="user:security",
        repo_root=_ROOT,
        run_id="run-perfbudget1",
    )
    started = time.monotonic()
    asyncio.run(orchestrator.run(state))
    elapsed_ms = int((time.monotonic() - started) * 1000)
    assert elapsed_ms < WORKFLOW_LATENCY_BUDGET_MS["pr_review"]
    timeline = build_timeline(sac_root, state.run_id)
    assert not check_workflow_budget(timeline)
