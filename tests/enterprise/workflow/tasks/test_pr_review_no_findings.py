"""PR review no-findings workflow tests."""

import asyncio
from pathlib import Path

from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus

_ROOT = Path(__file__).resolve().parents[4]


def test_pr_review_benign_fixture_is_low_risk_without_comment_proposal():
    sac_root = _ROOT / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="examples/enterprise/fixtures/pr_benign",
        actor_id="user:test",
        repo_root=_ROOT,
        run_id="run-prbenign01",
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.status == WorkflowStatus.succeeded
    assert final.risk_tier == RiskTier.low
    assert not final.findings
    assert all(item.kind != "comment" for item in final.proposals)
