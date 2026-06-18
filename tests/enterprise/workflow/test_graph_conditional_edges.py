"""Conditional routing uses deterministic state fields."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

from safecode.enterprise.workflow.graph import (
    CONDITIONAL_EDGES,
    REPAIR_OR_BLOCKER_NODE,
    _route_high_risk,
    _route_missing_evidence,
    _route_validation_failed,
)
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus


def _graph_state(state):
    return {"enterprise_state": state.model_dump(mode="python")}


def test_missing_evidence_routes_to_retrieve(tmp_path: Path):
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="x.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-route00001",
    )
    state = state.model_copy(update={"missing_evidence": True})
    assert _route_missing_evidence(_graph_state(state)) == CONDITIONAL_EDGES["missing_evidence"][1]


def test_high_risk_routes_to_approval_gate(tmp_path: Path):
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="x.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-route00002",
    )
    state = state.model_copy(update={"risk_tier": RiskTier.high})
    assert _route_high_risk(_graph_state(state)) == "approval_gate"


def test_validation_failed_routes_to_repair_or_blocker(tmp_path: Path):
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="x.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-route00003",
    )
    state = state.model_copy(update={"validation_failed": True})
    assert _route_validation_failed(_graph_state(state)) == REPAIR_OR_BLOCKER_NODE


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="langgraph optional extra not installed",
)
def test_local_and_langgraph_low_risk_equivalent(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKFLOW_RUNTIME", raising=False)
    sac_root = tmp_path / ".sac"
    base_kwargs = dict(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-equiv00001",
    )
    local_state = build_initial_state(**base_kwargs)
    local_final = asyncio.run(LocalOrchestrator(sac_root / "local", runtime="local").run(local_state))
    graph_final = asyncio.run(
        LocalOrchestrator(sac_root / "graph", runtime="langgraph").run(
            build_initial_state(**base_kwargs)
        )
    )
    assert local_final.status == WorkflowStatus.succeeded
    assert graph_final.status == WorkflowStatus.succeeded
    assert local_final.risk_tier == graph_final.risk_tier
    assert local_final.report is not None
    assert graph_final.report is not None
