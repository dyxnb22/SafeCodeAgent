"""Deterministic load profile budget tests (v2.5.5)."""

from __future__ import annotations

from safecode.enterprise.perf.budgets import (
    NODE_LATENCY_BUDGET_MS,
    WORKFLOW_LATENCY_BUDGET_MS,
    check_run_cost_budget,
    check_workflow_budget,
)
from safecode.enterprise.eval.cases import CostBudget
from safecode.enterprise.trace.timeline import RunTimeline, TimelineActor, TimelineNode, TimelineValidation
from safecode.enterprise.workflow.contracts import NodeCost, RunCosts

# Documented offline load profile (milliseconds) — kept under CI budgets.
LOAD_PROFILE_MS: dict[str, dict[str, int]] = {
    "pr_review": {
        "workflow": 18_000,
        "retrieve": 2_500,
        "analyze": 6_000,
        "validate": 4_000,
    },
    "remediation": {
        "workflow": 28_000,
        "retrieve": 3_000,
        "analyze": 8_000,
        "validate": 6_000,
    },
}


def _timeline(task_type: str, profile: dict[str, int]) -> RunTimeline:
    nodes = [
        TimelineNode(
            name=name,
            status="ok",
            started_at="2026-06-19T00:00:00+00:00",
            ended_at="2026-06-19T00:00:01+00:00",
            duration_ms=duration,
            summary=f"{name} complete",
        )
        for name, duration in profile.items()
        if name != "workflow"
    ]
    return RunTimeline(
        run_id=f"run-load-{task_type}",
        tenant_id="tenant-a",
        task_type=task_type,
        status="succeeded",
        actor=TimelineActor(actor_id="user:load"),
        policy_snapshot_id="policy-load",
        summary="load profile",
        started_at="2026-06-19T00:00:00+00:00",
        ended_at="2026-06-19T00:00:30+00:00",
        duration_ms=profile["workflow"],
        nodes=nodes,
        validation=TimelineValidation(ran=True, summary="within profile"),
    )


def test_documented_load_profile_stays_within_latency_budgets() -> None:
    for task_type, profile in LOAD_PROFILE_MS.items():
        timeline = _timeline(task_type, profile)
        assert profile["workflow"] < WORKFLOW_LATENCY_BUDGET_MS[task_type]
        assert not check_workflow_budget(timeline)
        for node in timeline.nodes:
            assert node.duration_ms < NODE_LATENCY_BUDGET_MS[node.name]


def test_load_profile_cost_envelope_within_default_budget() -> None:
    limits = CostBudget()
    for task_type, profile in LOAD_PROFILE_MS.items():
        costs = RunCosts(
            total=NodeCost(
                input_tokens=2_000,
                output_tokens=400,
                latency_ms=profile["workflow"],
            ),
            dollars_estimate=0.02,
        )
        assert not check_run_cost_budget(costs, limits), task_type
