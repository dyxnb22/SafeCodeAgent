"""Tests for trace emitter idempotency and persistence."""

from pathlib import Path

from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import MAX_PAYLOAD_FIELD_BYTES, TraceEventType, make_event_id


def test_emitter_writes_jsonl(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    emitter = TraceEmitter(sac_root, "run-0000000001")
    event = emitter.emit(
        TraceEventType.node_start,
        node_id="classify_request",
        seq=1,
        tenant_id="local",
        payload={"summary": "start"},
    )
    assert event is not None
    assert emitter.path.is_file()
    loaded = emitter.iter_events()
    assert len(loaded) == 1
    assert loaded[0].event_id == event.event_id


def test_re_emit_same_event_id_is_no_op(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    emitter = TraceEmitter(sac_root, "run-0000000001")
    event_id = make_event_id(run_id="run-0000000001", node_id="orchestrator", seq=1)
    first = emitter.emit(
        TraceEventType.workflow_start,
        node_id="orchestrator",
        seq=1,
        tenant_id="local",
        event_id=event_id,
        payload={"task_type": "pr_review"},
    )
    second = emitter.emit(
        TraceEventType.workflow_start,
        node_id="orchestrator",
        seq=1,
        tenant_id="local",
        event_id=event_id,
        payload={"task_type": "pr_review"},
    )
    assert first is not None
    assert second is None
    assert len(emitter.iter_events()) == 1


def test_emitter_redacts_secrets_and_truncates_large_fields(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    emitter = TraceEmitter(sac_root, "run-0000000001")
    secret = "token=ghp_" + ("a" * 40)
    large = "x" * 3000
    event = emitter.emit(
        TraceEventType.tool_executed,
        node_id="collect_repo_context",
        seq=2,
        tenant_id="local",
        payload={"secret": secret, "preview": large},
    )
    assert event is not None
    assert event.redaction_applied is True
    assert "[REDACTED]" in str(event.payload["secret"])
    assert len(str(event.payload["preview"]).encode("utf-8")) <= MAX_PAYLOAD_FIELD_BYTES + 16
