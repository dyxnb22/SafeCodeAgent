"""Shared helpers for deterministic workflow node stubs."""

from __future__ import annotations

from datetime import datetime, timezone

from safecode.enterprise.workflow.contracts import NodeCost, NodePatch, NodeOutput, TraceEventDraft
from safecode.enterprise.workflow.state import EnterpriseRunState


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def trace_event(state: EnterpriseRunState, node_name: str, kind: str = "node.end") -> TraceEventDraft:
    return TraceEventDraft(
        event_id=f"{state.run_id}:{node_name}:{kind}",
        kind=kind,
        payload={"run_id": state.run_id, "node_name": node_name, "tenant_id": state.tenant_id},
    )


def build_patch(
    state: EnterpriseRunState,
    node_name: str,
    *,
    summary: str,
    state_updates: dict | None = None,
    status: str = "ok",
) -> NodePatch:
    updates = dict(state_updates or {})
    node_outputs = dict(state.node_outputs)
    node_outputs[node_name] = NodeOutput(
        node_name=node_name,
        status="ok",
        summary=summary,
        started_at=state.updated_at,
        ended_at=utc_now_iso(),
    )
    updates["node_outputs"] = node_outputs
    updates["updated_at"] = utc_now_iso()
    return NodePatch(
        node_name=node_name,
        status=status,
        state_updates=updates,
        events=[trace_event(state, node_name)],
        cost=NodeCost(latency_ms=1, request_count=1),
        duration_ms=1,
    )
