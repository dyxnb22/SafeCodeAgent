"""Trace event schema for enterprise workflow observability.

中文模块说明：TraceEvent 类型与 TraceEventType 枚举，描述节点级可观测事件。
- 架构位置：Observability 数据契约；timeline 与 console 视图的来源。
- 安全不变量：事件 payload 可能含敏感字段，导出前须经 redaction profile。
- 学习路径：对照 ``contracts/snapshots/trace_event.json``。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.workflow.contracts import NodeCost

TRACE_SCHEMA_VERSION = 1
MAX_PAYLOAD_FIELD_BYTES = 2048

TracePayloadValue = str | int | float | bool | list[Any]


class TraceEventType(str, Enum):
    workflow_start = "workflow.start"
    workflow_end = "workflow.end"
    node_start = "node.start"
    node_end = "node.end"
    retrieval_query = "retrieval.query"
    retrieval_citation_used = "retrieval.citation_used"
    retrieval_permission_denied = "retrieval.permission_denied"
    model_call_start = "model.call_start"
    model_call_end = "model.call_end"
    model_validation_fail = "model.validation_fail"
    tool_proposed = "tool.proposed"
    tool_blocked = "tool.blocked"
    tool_executed = "tool.executed"
    sandbox_proposal = "sandbox.proposal"
    sandbox_executed = "sandbox.executed"
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"
    approval_consumed = "approval.consumed"
    approval_rejected = "approval.rejected"
    policy_block = "policy.block"
    policy_project_override_blocked = "policy.project_override_blocked"
    patch_proposed = "patch.proposed"
    patch_applied = "patch.applied"
    rollback_executed = "rollback.executed"
    validation_run = "validation.run"
    validation_result = "validation.result"
    failure_recorded = "failure.recorded"
    memory_fact_used = "memory.fact_used"
    memory_injection_blocked = "memory.injection_blocked"
    redaction_hit = "redaction.hit"
    audit_anchor_written = "audit.anchor_written"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_event_id(*, run_id: str, node_id: str, seq: int) -> str:
    digest = hashlib.sha256(f"{run_id}:{node_id}:{seq}".encode("utf-8")).hexdigest()[:24]
    return f"evt-{digest}"


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    run_id: str
    tenant_id: str
    node_id: str
    seq: int = Field(ge=0)
    type: TraceEventType
    timestamp: str
    actor_id: str | None = None
    policy_snapshot_id: str | None = None
    payload: dict[str, TracePayloadValue] = Field(default_factory=dict)
    redaction_applied: bool = False
    redaction_reason: str | None = None
    cost: NodeCost | None = None
    duration_ms: int | None = None
    schema_version: int = TRACE_SCHEMA_VERSION


@dataclass
class TraceContext:
    """Run-scoped context passed to nodes and the approval engine."""

    sac_root: Path
    run_id: str
    tenant_id: str
    actor_id: str | None
    policy_snapshot_id: str | None
    seq: int = field(default=0)

    def bump_seq(self) -> int:
        self.seq += 1
        return self.seq
