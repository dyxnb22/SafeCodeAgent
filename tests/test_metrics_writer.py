"""Tests for v3.10.0 live-session metrics writer.

Covers:
- Disabled by default (no env var)
- Enabled via SAFECODE_METRICS=1
- Events written as JSONL
- Never raises into user workflow
- Size bound enforced
- Redaction (no raw task text in size field)
- make_metrics_writer factory is safe
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from safecode.metrics.writer import (
    MetricsEvent,
    MetricsWriter,
    _ENV_KEY,
    _MAX_SESSION_BYTES,
    _METRICS_FILENAME,
    make_metrics_writer,
)


# ── Disabled by default ───────────────────────────────────────────────────


class TestMetricsWriterDisabledByDefault:
    def test_disabled_when_no_env_var(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        w = MetricsWriter(tmp_path, "sess-1")
        assert not w.enabled

    def test_no_file_written_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        w = MetricsWriter(tmp_path, "sess-1")
        w.record_step_start(0, "edit")
        assert not (tmp_path / ".sac" / _METRICS_FILENAME).exists()

    def test_write_event_noop_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        w = MetricsWriter(tmp_path, "sess-1")
        event = MetricsEvent(event_type="step_start", session_id="s")
        w.write_event(event)  # must not raise


# ── Enabled via env var ───────────────────────────────────────────────────


class TestMetricsWriterEnabled:
    def test_enabled_via_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        assert w.enabled

    def test_path_is_in_sac_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        assert w.path is not None
        assert w.path.parent == tmp_path / ".sac"

    def test_event_written_as_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        w.record_step_start(0, "edit")
        lines = (tmp_path / ".sac" / _METRICS_FILENAME).read_text().strip().splitlines()
        assert len(lines) >= 1
        event = json.loads(lines[0])
        assert event["event_type"] == "step_start"
        assert event["session_id"] == "sess-1"

    def test_multiple_events_appended(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        w.record_step_start(0, "edit")
        w.record_step_end(0, "edit")
        lines = (tmp_path / ".sac" / _METRICS_FILENAME).read_text().strip().splitlines()
        assert len(lines) == 2

    def test_step_field_present(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        w.record_step_start(5)
        lines = (tmp_path / ".sac" / _METRICS_FILENAME).read_text().strip().splitlines()
        event = json.loads(lines[0])
        assert event["step"] == 5

    def test_tool_intent_field(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        w.record_step_start(0, "patch")
        event = json.loads((tmp_path / ".sac" / _METRICS_FILENAME).read_text().splitlines()[0])
        assert event["tool_intent"] == "patch"

    def test_pending_patch_records_size_not_content(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        secret_text = "my-secret-api-key patch content"
        w.record_pending_patch(0, secret_text)
        raw = (tmp_path / ".sac" / _METRICS_FILENAME).read_text()
        assert "my-secret-api-key" not in raw
        event = json.loads(raw.splitlines()[0])
        assert event["pending_patch_size"] == len(secret_text.encode("utf-8"))

    def test_retry_event(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1")
        w.record_retry(3, retry_count=1)
        event = json.loads((tmp_path / ".sac" / _METRICS_FILENAME).read_text().splitlines()[0])
        assert event["event_type"] == "retry"
        assert event["retry_count"] == 1


# ── Size bound ────────────────────────────────────────────────────────────


class TestMetricsWriterSizeBound:
    def test_stops_writing_after_max_bytes(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1", max_bytes=100)
        for i in range(200):
            w.record_step_start(i)
        size = (tmp_path / ".sac" / _METRICS_FILENAME).stat().st_size
        assert size <= 120  # slightly over due to final write

    def test_default_max_bytes_is_1mib(self):
        assert _MAX_SESSION_BYTES == 1024 * 1024


# ── Never raises ─────────────────────────────────────────────────────────


class TestMetricsWriterNeverRaises:
    def test_write_to_unwritable_path_silently_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        # Create a writer then break the path
        w = MetricsWriter(tmp_path, "sess-1")
        w._path = Path("/nonexistent/path/metrics.jsonl")
        w.write_event(MetricsEvent("step_start", "s"))  # must not raise

    def test_factory_never_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = make_metrics_writer(tmp_path, "sess-1")
        assert w is not None

    def test_factory_disabled_returns_noop_writer(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        w = make_metrics_writer(tmp_path, "sess-1")
        w.record_step_start(0)  # must not raise


# ── MetricsEvent model ────────────────────────────────────────────────────


class TestMetricsEvent:
    def test_to_dict_has_required_keys(self):
        e = MetricsEvent(event_type="step_start", session_id="abc")
        d = e.to_dict()
        assert d["event_type"] == "step_start"
        assert d["session_id"] == "abc"
        assert "ts" in d

    def test_optional_fields_absent_when_none(self):
        e = MetricsEvent(event_type="step_end", session_id="s")
        d = e.to_dict()
        assert "step" not in d
        assert "tool_intent" not in d

    def test_optional_fields_present_when_set(self):
        e = MetricsEvent(event_type="retry", session_id="s", step=2, retry_count=1)
        d = e.to_dict()
        assert d["step"] == 2
        assert d["retry_count"] == 1

    def test_to_dict_is_json_serializable(self):
        e = MetricsEvent("step_start", "s", step=0, tool_intent="edit")
        assert json.dumps(e.to_dict())


# ── Explicit-enabled flag overrides env ───────────────────────────────────


class TestMetricsWriterExplicitEnabled:
    def test_explicit_true_overrides_no_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        w = MetricsWriter(tmp_path, "sess-1", enabled=True)
        assert w.enabled

    def test_explicit_false_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "1")
        w = MetricsWriter(tmp_path, "sess-1", enabled=False)
        assert not w.enabled
