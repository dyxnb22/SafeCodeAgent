"""Tests for workflow enum types (v1.2.1-T1)."""

from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus


def test_task_type_values():
    assert TaskType.pr_review.value == "pr_review"
    assert TaskType.compliance_export.value == "compliance_export"


def test_risk_tier_values():
    assert {item.value for item in RiskTier} == {"low", "medium", "high", "critical"}


def test_workflow_status_values():
    assert WorkflowStatus.awaiting_approval.value == "awaiting_approval"
    assert WorkflowStatus.rejected.value == "rejected"
