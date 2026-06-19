"""Enterprise workflow enum types."""

from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    pr_review = "pr_review"
    remediation = "remediation"
    secure_planning = "secure_planning"
    compliance_export = "compliance_export"


class WorkflowStatus(str, Enum):
    pending = "pending"
    running = "running"
    awaiting_approval = "awaiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    rejected = "rejected"
    blocked = "blocked"
    cancelled = "cancelled"


class RiskTier(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
