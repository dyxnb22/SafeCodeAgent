"""Workflow latency budget checks."""

from __future__ import annotations

from safecode.enterprise.trace.timeline import RunTimeline

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
