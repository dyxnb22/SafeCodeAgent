"""Node contract tests (v1.2.1-T3)."""

import asyncio
import inspect

import pytest

from safecode.enterprise.workflow.contracts import NodePatch, TraceEventDraft
from safecode.enterprise.workflow.nodes.registry import NODE_RUNNERS, WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.state import EnterpriseRunState, RBACSubject, RepoContext, RunRequest
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _state(**extra) -> EnterpriseRunState:
    base = EnterpriseRunState(
        run_id="run-nodecontract1",
        task_type=TaskType.pr_review,
        status=WorkflowStatus.running,
        actor_id="user:test",
        subject=RBACSubject(actor_id="user:test"),
        policy_snapshot_id="snapshot-test",
        request=RunRequest(
            task_type=TaskType.pr_review,
            input_kind="pr_fixture",
            input_ref="fixture.json",
            actor_id="user:test",
            extra=extra,
        ),
        repo=RepoContext(repo_root="/tmp/repo"),
        created_at="2026-06-19T00:00:00+00:00",
        updated_at="2026-06-19T00:00:00+00:00",
    )
    return base


@pytest.mark.parametrize("node_name", WORKFLOW_NODE_ORDER)
def test_node_exports_async_run_contract(node_name: str):
    runner = NODE_RUNNERS[node_name]
    assert inspect.iscoroutinefunction(runner)
    before = _state()
    before_dump = before.model_dump()
    patch = asyncio.run(runner(before))
    assert isinstance(patch, NodePatch)
    assert patch.node_name in WORKFLOW_NODE_ORDER
    assert patch.events
    assert all(isinstance(event, TraceEventDraft) for event in patch.events)
    assert before.model_dump() == before_dump


def test_analyze_node_sets_risk_tier_without_mutating_input():
    state = _state(high_risk="1")
    snapshot = state.model_dump()
    patch = asyncio.run(NODE_RUNNERS["analyze_security_risk"](state))
    assert patch.state_updates["risk_tier"].value == "high"
    assert state.model_dump() == snapshot
