"""Run cost budget enforcement tests (v2.5.3)."""

from __future__ import annotations

from safecode.enterprise.eval.cases import CostBudget
from safecode.enterprise.perf.budgets import check_run_cost_budget
from safecode.enterprise.workflow.contracts import NodeCost, RunCosts


def test_cost_budget_passes_within_limits() -> None:
    costs = RunCosts(
        total=NodeCost(input_tokens=100, output_tokens=50, latency_ms=1000),
        dollars_estimate=0.01,
    )
    limits = CostBudget(
        max_input_tokens=1000,
        max_output_tokens=500,
        max_latency_ms=5000,
        max_dollars=0.05,
    )
    assert not check_run_cost_budget(costs, limits)


def test_cost_budget_flags_token_overrun() -> None:
    costs = RunCosts(total=NodeCost(input_tokens=9000, output_tokens=10, latency_ms=10))
    limits = CostBudget(max_input_tokens=6000)
    failures = check_run_cost_budget(costs, limits)
    assert any("input_tokens" in item for item in failures)


def test_cost_budget_flags_latency_and_dollars() -> None:
    costs = RunCosts(
        total=NodeCost(latency_ms=60_000),
        dollars_estimate=0.25,
    )
    limits = CostBudget(max_latency_ms=30_000, max_dollars=0.05)
    failures = check_run_cost_budget(costs, limits)
    assert any("latency_ms" in item for item in failures)
    assert any("dollars_estimate" in item for item in failures)
