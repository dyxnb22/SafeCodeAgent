"""Run-scoped trace session with optional audit dual-write."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEvent, TraceEventType, make_event_id
from safecode.enterprise.workflow.contracts import NodeCost

if TYPE_CHECKING:
    from safecode.enterprise.workflow.state import EnterpriseRunState

_AUDIT_KIND_BY_TRACE: dict[TraceEventType, AuditEventKind] = {
    TraceEventType.workflow_start: AuditEventKind.workflow_start,
    TraceEventType.workflow_end: AuditEventKind.workflow_end,
    TraceEventType.node_start: AuditEventKind.node_start,
    TraceEventType.node_end: AuditEventKind.node_end,
    TraceEventType.approval_requested: AuditEventKind.approval_requested,
    TraceEventType.approval_decided: AuditEventKind.approval_decided,
    TraceEventType.approval_consumed: AuditEventKind.approval_consumed,
    TraceEventType.tool_proposed: AuditEventKind.tool_call_proposed,
    TraceEventType.tool_blocked: AuditEventKind.tool_call_blocked,
    TraceEventType.tool_executed: AuditEventKind.tool_call_executed,
    TraceEventType.policy_block: AuditEventKind.policy_block,
    TraceEventType.policy_project_override_blocked: AuditEventKind.project_override_blocked,
    TraceEventType.sandbox_proposal: AuditEventKind.sandbox_proposal,
    TraceEventType.sandbox_executed: AuditEventKind.sandbox_executed,
    TraceEventType.patch_proposed: AuditEventKind.patch_proposed,
    TraceEventType.patch_applied: AuditEventKind.patch_applied,
    TraceEventType.rollback_executed: AuditEventKind.rollback_executed,
    TraceEventType.audit_anchor_written: AuditEventKind.audit_anchor_written,
}


def project_root_for_sac(sac_root: Path) -> Path:
    if sac_root.name == ".sac":
        return sac_root.parent
    return sac_root


class TraceSession:
    """Coordinates trace emission and overlapping audit events for one run."""

    def __init__(
        self,
        sac_root: Path,
        state: EnterpriseRunState,
        *,
        audit: EnterpriseAuditChain | None = None,
    ) -> None:
        self.sac_root = sac_root
        self.state = state
        self.emitter = TraceEmitter(sac_root, state.run_id)
        self.audit = audit or EnterpriseAuditChain(project_root_for_sac(sac_root))

    @property
    def path(self) -> Path:
        return self.emitter.path

    def emit(
        self,
        event_type: TraceEventType,
        *,
        node_id: str,
        payload: dict[str, object] | None = None,
        cost: NodeCost | None = None,
        duration_ms: int | None = None,
        event_id: str | None = None,
        audit: bool = True,
    ) -> TraceEvent | None:
        seq = self.emitter.allocate_seq()
        resolved_event_id = event_id or make_event_id(
            run_id=self.state.run_id,
            node_id=node_id,
            seq=seq,
        )
        event = self.emitter.emit(
            event_type,
            node_id=node_id,
            seq=seq,
            tenant_id=self.state.tenant_id,
            actor_id=self.state.actor_id,
            policy_snapshot_id=self.state.policy_snapshot_id,
            payload=payload,
            cost=cost,
            duration_ms=duration_ms,
            event_id=resolved_event_id,
        )
        if event is None:
            return None
        if audit:
            audit_kind = _AUDIT_KIND_BY_TRACE.get(event_type)
            if audit_kind is not None:
                audit_payload = {"event_id": resolved_event_id}
                if payload:
                    audit_payload.update({key: str(value) for key, value in payload.items()})
                self.audit.emit(
                    audit_kind,
                    run_id=self.state.run_id,
                    actor_id=self.state.actor_id or "unknown",
                    tenant_id=self.state.tenant_id,
                    payload=audit_payload,
                )
        return event

    def emit_run_trace(
        self,
        event_type: TraceEventType,
        *,
        node_id: str,
        tenant_id: str,
        actor_id: str | None,
        policy_snapshot_id: str | None,
        payload: dict[str, object] | None = None,
        audit: bool = True,
    ) -> TraceEvent | None:
        """Emit when only run metadata is available (e.g. approval store)."""
        seq = self.emitter.allocate_seq()
        resolved_event_id = make_event_id(
            run_id=self.state.run_id,
            node_id=node_id,
            seq=seq,
        )
        event = self.emitter.emit(
            event_type,
            node_id=node_id,
            seq=seq,
            tenant_id=tenant_id,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload=payload,
            event_id=resolved_event_id,
        )
        if event is None or not audit:
            return event
        audit_kind = _AUDIT_KIND_BY_TRACE.get(event_type)
        if audit_kind is not None:
            audit_payload = {"event_id": resolved_event_id}
            if payload:
                audit_payload.update({key: str(value) for key, value in payload.items()})
            self.audit.emit(
                audit_kind,
                run_id=self.state.run_id,
                actor_id=actor_id or "unknown",
                tenant_id=tenant_id,
                payload=audit_payload,
            )
        return event


def emit_standalone_trace(
    sac_root: Path,
    *,
    run_id: str,
    tenant_id: str,
    event_type: TraceEventType,
    node_id: str,
    actor_id: str | None,
    policy_snapshot_id: str | None,
    payload: dict[str, object] | None = None,
) -> TraceEvent | None:
    """Emit a trace event outside the orchestrator loop (approval store, CLI)."""
    emitter = TraceEmitter(sac_root, run_id)
    seq = emitter.allocate_seq()
    resolved_event_id = make_event_id(run_id=run_id, node_id=node_id, seq=seq)
    event = emitter.emit(
        event_type,
        node_id=node_id,
        seq=seq,
        tenant_id=tenant_id,
        actor_id=actor_id,
        policy_snapshot_id=policy_snapshot_id,
        payload=payload,
        event_id=resolved_event_id,
    )
    if event is None:
        return None
    audit_kind = _AUDIT_KIND_BY_TRACE.get(event_type)
    if audit_kind is not None:
        audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
        audit_payload = {"event_id": resolved_event_id}
        if payload:
            audit_payload.update({key: str(value) for key, value in payload.items()})
        audit.emit(
            audit_kind,
            run_id=run_id,
            actor_id=actor_id or "unknown",
            tenant_id=tenant_id,
            payload=audit_payload,
        )
    return event
