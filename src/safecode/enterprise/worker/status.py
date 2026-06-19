"""Workflow terminal status helpers."""

from __future__ import annotations

from safecode.enterprise.workflow.types import WorkflowStatus

TERMINAL_STATUSES: frozenset[WorkflowStatus] = frozenset(
    {
        WorkflowStatus.succeeded,
        WorkflowStatus.failed,
        WorkflowStatus.rejected,
        WorkflowStatus.blocked,
        WorkflowStatus.cancelled,
    }
)


def is_terminal(status: WorkflowStatus) -> bool:
    return status in TERMINAL_STATUSES
