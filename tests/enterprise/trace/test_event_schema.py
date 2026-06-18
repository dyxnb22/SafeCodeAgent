"""Tests for TraceEvent schema."""

from safecode.enterprise.trace.events import (
    TRACE_SCHEMA_VERSION,
    TraceEvent,
    TraceEventType,
    make_event_id,
)
from safecode.enterprise.workflow.contracts import NodeCost


def test_trace_event_required_fields():
    event = TraceEvent(
        event_id="evt-abc",
        run_id="run-0000000001",
        tenant_id="local",
        node_id="classify_request",
        seq=1,
        type=TraceEventType.node_end,
        timestamp="2026-06-19T12:00:00+00:00",
        payload={"summary": "ok"},
        redaction_applied=False,
    )
    assert event.run_id == "run-0000000001"
    assert event.node_id == "classify_request"
    assert event.type == TraceEventType.node_end
    assert event.payload == {"summary": "ok"}
    assert event.redaction_applied is False
    assert event.schema_version == TRACE_SCHEMA_VERSION


def test_make_event_id_is_deterministic():
    first = make_event_id(run_id="run-0000000001", node_id="orchestrator", seq=3)
    second = make_event_id(run_id="run-0000000001", node_id="orchestrator", seq=3)
    different = make_event_id(run_id="run-0000000001", node_id="orchestrator", seq=4)
    assert first == second
    assert first.startswith("evt-")
    assert len(first) == len("evt-") + 24
    assert first != different


def test_trace_event_optional_cost_and_duration():
    event = TraceEvent(
        event_id="evt-cost",
        run_id="run-0000000001",
        tenant_id="local",
        node_id="finalize",
        seq=9,
        type=TraceEventType.workflow_end,
        timestamp="2026-06-19T12:00:00+00:00",
        cost=NodeCost(input_tokens=10, output_tokens=5, latency_ms=42),
        duration_ms=42,
    )
    assert event.cost is not None
    assert event.cost.input_tokens == 10
    assert event.duration_ms == 42
