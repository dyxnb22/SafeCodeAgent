"""OpenTelemetry export tests (v2.5.1-T1)."""

from __future__ import annotations

import pytest

from safecode.enterprise.api.exceptions import SettingsValidationError
from safecode.enterprise.api.settings import TeamServerSettings
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.otel_exporter import (
    InMemoryOtelExporter,
    OtelExportConfig,
    RecordingOtelExporter,
    build_otel_exporter,
    parse_otel_enabled,
    validate_otel_config,
)


RUN_ID = "run-otel0001"


def test_otel_disabled_preserves_local_trace_only(tmp_path):
    emitter = TraceEmitter(tmp_path, RUN_ID)
    event = emitter.emit(
        TraceEventType.node_start,
        node_id="collect_repo_context",
        seq=1,
        tenant_id="tenant-a",
        payload={"api_key": "ghp_deadbeefdeadbeefdeadbeefdeadbeef"},
    )
    assert event is not None
    assert emitter.path.is_file()
    assert "ghp_" not in emitter.path.read_text(encoding="utf-8")


def test_otel_enabled_exports_redacted_spans(tmp_path):
    collector = InMemoryOtelExporter()
    emitter = TraceEmitter(
        tmp_path,
        RUN_ID,
        otel_exporter=collector,
        otel_service_name="safecode-test",
    )
    emitter.emit(
        TraceEventType.node_start,
        node_id="retrieve_policy_and_code",
        seq=1,
        tenant_id="tenant-a",
        payload={"secret": "sk-live-secret-value", "node": "retrieve"},
    )
    assert len(collector.spans) == 1
    span = collector.spans[0]
    assert span.service_name == "safecode-test"
    assert "sk-live" not in str(span.attributes)
    assert span.attributes["payload.node"] == "retrieve"


def test_otel_export_failure_does_not_block_local_trace(tmp_path):
    collector = InMemoryOtelExporter(fail_on_export=True)
    emitter = TraceEmitter(tmp_path, "run-otel0002", otel_exporter=collector)
    event = emitter.emit(
        TraceEventType.workflow_end,
        node_id="finalize",
        seq=2,
        tenant_id="tenant-a",
    )
    assert event is not None
    assert emitter.path.is_file()


def test_malformed_otel_config_fails_closed():
    with pytest.raises(SettingsValidationError, match="endpoint"):
        validate_otel_config(OtelExportConfig(enabled=True, endpoint=None))
    with pytest.raises(SettingsValidationError):
        parse_otel_enabled("maybe")


def test_team_server_settings_reject_enabled_otel_without_endpoint():
    with pytest.raises(SettingsValidationError, match="otel endpoint"):
        TeamServerSettings.model_validate({"otel_enabled": True})


def test_build_otel_exporter_returns_none_when_disabled():
    assert build_otel_exporter(OtelExportConfig(enabled=False)) is None


def test_recording_exporter_validates_endpoint():
    exporter = RecordingOtelExporter(endpoint="http://127.0.0.1:4318/v1/traces", service_name="svc")
    exporter.export_span(
        __import__(
            "safecode.enterprise.trace.otel_exporter", fromlist=["OtelSpanRecord"]
        ).OtelSpanRecord(
            name="trace.node.start",
            run_id="run-a",
            tenant_id="tenant-a",
            service_name="svc",
            event_id="evt-1",
            event_type="node.start",
            attributes={"node_id": "plan_actions"},
        )
    )
    assert len(exporter.spans) == 1
