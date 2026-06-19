"""GitHub PR comment writer (fixture-first, approval-gated)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from safecode.context.redactor import redact_secrets
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import emit_standalone_trace
from safecode.enterprise.workflow.state import ApprovalDecision, ApprovalDecisionInputs, ToolCallRecord


class PRCommentWriteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixture", "live"] = "fixture"
    output_path: str | None = None
    owner: str | None = None
    repo: str | None = None
    pr_number: int | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def post_pr_comment(
    *,
    sac_root: Path,
    run_id: str,
    node_name: str,
    spec: PRCommentWriteSpec,
    body: str,
    approved: bool,
    actor_id: str,
    tenant_id: str = "local",
    policy_snapshot_id: str = "snapshot-local",
) -> ToolCallRecord:
    """Write a PR comment offline or record a gated live write attempt."""
    redacted_body = redact_secrets(body)
    call_id = f"tool-{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    decision = ApprovalDecision(
        decision="GATE" if spec.mode == "live" else "AUTO",
        reason="fixture write" if spec.mode == "fixture" else "live github write",
        policy_snapshot_id=policy_snapshot_id,
        inputs=ApprovalDecisionInputs(policy_value="GATE", rbac_value="GATE", tool_spec_value="GATE"),
    )
    record = ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="github_write",
        tool_category="write_network" if spec.mode == "live" else "write_local",
        inputs_redacted={"mode": spec.mode, "body": redacted_body[:512]},
        decision=decision,
        started_at=started,
    )

    if spec.mode == "live" and not approved:
        record.outcome = "blocked"
        record.ended_at = _utc_now()
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            event_type=TraceEventType.tool_blocked,
            node_id=node_name,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload={"tool_name": "github_write", "mode": "live"},
        )
        return record

    if spec.mode == "fixture":
        if not spec.output_path:
            raise ValueError("output_path is required for fixture mode")
        path = Path(spec.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redacted_body, encoding="utf-8")
        record.outcome = "ok"
        record.output_excerpt = redacted_body[:256]
        record.ended_at = _utc_now()
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            event_type=TraceEventType.tool_executed,
            node_id=node_name,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload={"tool_name": "github_write", "mode": "fixture", "path": str(path)},
        )
        return record

    # Live mode with approval: record execution without network I/O in v1.7.
    record.outcome = "ok"
    record.output_excerpt = "live write recorded (offline default)"
    record.ended_at = _utc_now()
    emit_standalone_trace(
        sac_root,
        run_id=run_id,
        tenant_id=tenant_id,
        event_type=TraceEventType.tool_executed,
        node_id=node_name,
        actor_id=actor_id,
        policy_snapshot_id=policy_snapshot_id,
        payload={"tool_name": "github_write", "mode": "live", "actor": actor_id},
    )
    return record
