"""Workflow trace emission tests."""

import asyncio
from pathlib import Path

from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def test_workflow_run_emits_start_node_and_end_events(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-trace00001"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.status == WorkflowStatus.succeeded

    emitter = TraceEmitter(sac_root, run_id)
    events = emitter.iter_events()
    types = [event.type for event in events]
    assert types[0] == TraceEventType.workflow_start
    assert types[-1] == TraceEventType.workflow_end
    assert types.count(TraceEventType.node_start) == len(WORKFLOW_NODE_ORDER)
    assert types.count(TraceEventType.node_end) == len(WORKFLOW_NODE_ORDER)

    node_starts = [event.node_id for event in events if event.type == TraceEventType.node_start]
    assert node_starts == list(WORKFLOW_NODE_ORDER)

    for event in events:
        assert event.run_id == run_id
        assert event.redaction_applied in {True, False}
        assert event.seq >= 1
