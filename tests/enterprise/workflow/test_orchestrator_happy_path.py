"""Orchestrator happy-path tests (v1.2.2-T1)."""

import asyncio
from pathlib import Path

from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def test_orchestrator_runs_nine_nodes_in_order(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-happy00001",
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.status == WorkflowStatus.succeeded
    assert list(final.node_outputs) == list(WORKFLOW_NODE_ORDER)
    checkpoint = load_checkpoint(sac_root, final.run_id)
    assert checkpoint.completed_nodes == list(WORKFLOW_NODE_ORDER)
    assert checkpoint.next_node is None
