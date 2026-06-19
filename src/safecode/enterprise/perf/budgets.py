"""Workflow latency and cost budget checks."""

from __future__ import annotations

from safecode.enterprise.eval.cases import CostBudget
from safecode.enterprise.trace.timeline import RunTimeline
from safecode.enterprise.workflow.contracts import RunCosts

WORKFLOW_LATENCY_BUDGET_MS: dict[str, int] = {
    "pr_review": 30_000,
    "remediation": 45_000,
}

NODE_LATENCY_BUDGET_MS: dict[str, int] = {
    "retrieve": 5_000,
    "analyze": 10_000,
    "validate": 10_000,
}


def check_workflow_budget(timeline: RunTimeline) -> list[str]:
    """Return budget violation messages; empty list means within budget."""
    failures: list[str] = []
    workflow_limit = WORKFLOW_LATENCY_BUDGET_MS.get(timeline.task_type)
    if workflow_limit is not None and timeline.duration_ms > workflow_limit:
        failures.append(
            f"{timeline.task_type} duration {timeline.duration_ms}ms exceeds budget {workflow_limit}ms"
        )
    for node in timeline.nodes:
        limit = NODE_LATENCY_BUDGET_MS.get(node.name)
        if limit is not None and node.duration_ms > limit:
            failures.append(
                f"node {node.name} duration {node.duration_ms}ms exceeds budget {limit}ms"
            )
    return failures


def check_run_cost_budget(costs: RunCosts, limits: CostBudget) -> list[str]:
    """Return budget violation messages; empty list means within budget."""
    failures: list[str] = []
    total = costs.total
    if total.input_tokens > limits.max_input_tokens:
        failures.append(
            f"input_tokens {total.input_tokens} exceeds budget {limits.max_input_tokens}"
        )
    if total.output_tokens > limits.max_output_tokens:
        failures.append(
            f"output_tokens {total.output_tokens} exceeds budget {limits.max_output_tokens}"
        )
    if total.latency_ms > limits.max_latency_ms:
        failures.append(
            f"latency_ms {total.latency_ms} exceeds budget {limits.max_latency_ms}"
        )
    if costs.dollars_estimate is not None and costs.dollars_estimate > limits.max_dollars:
        failures.append(
            f"dollars_estimate {costs.dollars_estimate} exceeds budget {limits.max_dollars}"
        )
    return failures
