"""Approval trace emission tests."""

import asyncio
from pathlib import Path

import pytest

from safecode.enterprise.approvals.engine import decide_with_trace
from safecode.enterprise.approvals.store import (
    Action,
    consume_grant,
    decide_request,
    save_grant,
    save_request,
    ApprovalRequest,
    Grant,
)
from safecode.enterprise.policy.models import PolicyLayer, PolicySnapshot, PolicyValue
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import TraceSession
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType


def _policy_snapshot() -> PolicySnapshot:
    return PolicySnapshot(
        snapshot_id="pol-test",
        layers=(
            PolicyLayer(
                name="org",
                source_ref="test",
                values={"file_write": PolicyValue(key="file_write", value="GATE")},
            ),
        ),
        merged={"file_write": PolicyValue(key="file_write", value="GATE")},
        created_at="2026-06-19T00:00:00+00:00",
    )


def test_save_and_decide_request_emit_approval_trace(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-approval01"
    request = ApprovalRequest(
        request_id="approval-run-approval01",
        run_id=run_id,
        action=Action.file_write,
        risk_tier="high",
        requested_by_node="approval_gate",
        requesting_actor="user:test",
        policy_snapshot_id="pol-test",
        created_at="2026-06-19T00:00:00+00:00",
        preview="write report",
    )
    save_request(sac_root, request)
    decide_request(
        sac_root,
        run_id,
        request.request_id,
        decision="approved",
        decision_actor="user:approver",
    )
    events = TraceEmitter(sac_root, run_id).iter_events()
    types = [event.type for event in events]
    assert TraceEventType.approval_requested in types
    assert TraceEventType.approval_decided in types


def test_consume_grant_emits_approval_consumed(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-grant0001"
    grant = Grant(
        grant_id="grant-run-grant01",
        run_id=run_id,
        request_id="approval-run-grant0001",
        action=Action.file_write,
        policy_snapshot_id="pol-test",
        created_at="2026-06-19T00:00:00+00:00",
    )
    save_grant(sac_root, grant)
    consume_grant(sac_root, run_id, grant.grant_id)
    events = TraceEmitter(sac_root, run_id).iter_events()
    assert any(event.type == TraceEventType.approval_consumed for event in events)


def test_decide_with_trace_records_engine_evaluation(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:dev",
        repo_root=tmp_path,
        run_id="run-engine001",
    )
    session = TraceSession(sac_root, state)
    decision = decide_with_trace(
        session,
        Action.file_write,
        policy_snapshot=_policy_snapshot(),
        subject=RBACSubject(actor_id="user:dev", tenant_id="local", roles=["developer"]),
        risk_tier="high",
    )
    assert decision.decision == "BLOCK"
    events = session.emitter.iter_events()
    assert len(events) == 1
    assert events[0].type == TraceEventType.policy_block


def test_high_risk_interrupt_includes_approval_requested_trace(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-highrisk02"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        extra={"high_risk": "1"},
    )
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))
    events = TraceEmitter(sac_root, run_id).iter_events()
    assert any(event.type == TraceEventType.approval_requested for event in events)
    assert not any(event.type == TraceEventType.workflow_end for event in events)
