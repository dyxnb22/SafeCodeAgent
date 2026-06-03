"""Tests for src/safecode/otel/exporter.py (v3.6.2).

Invariants verified:
- Disabled by default (no SAFECODE_OTEL_EXPORTER env var).
- No telemetry emitted in any test; all OTel SDK calls are mocked.
- RuntimeWarning when env var set but OTel packages missing.
- Graceful degradation when OTLP exporter package missing.
- export_event() never raises.
- Endpoint string never appears in warning messages.
- is_enabled() is authoritative.
"""

from __future__ import annotations

import os
import warnings
from contextlib import contextmanager
from typing import Generator
from unittest.mock import MagicMock, patch, call

import pytest

from safecode.otel.exporter import OtelExporter, OtelExportResult, _ENV_KEY


# ── helpers ──────────────────────────────────────────────────────────────────

@contextmanager
def _otel_env(endpoint: str) -> Generator[None, None, None]:
    """Context manager that sets SAFECODE_OTEL_EXPORTER and unsets it after."""
    original = os.environ.get(_ENV_KEY)
    os.environ[_ENV_KEY] = endpoint
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(_ENV_KEY, None)
        else:
            os.environ[_ENV_KEY] = original


@contextmanager
def _no_otel_env() -> Generator[None, None, None]:
    """Context manager that ensures SAFECODE_OTEL_EXPORTER is absent."""
    original = os.environ.pop(_ENV_KEY, None)
    try:
        yield
    finally:
        if original is not None:
            os.environ[_ENV_KEY] = original


# ── default disabled behaviour ────────────────────────────────────────────────

class TestDefaultDisabled:
    def test_from_env_disabled_when_no_var(self) -> None:
        with _no_otel_env():
            exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()

    def test_from_env_disabled_when_empty_var(self) -> None:
        with _otel_env(""):
            exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()

    def test_from_env_disabled_when_whitespace_var(self) -> None:
        with _otel_env("   "):
            exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()

    def test_constructor_default_disabled(self) -> None:
        exporter = OtelExporter()
        assert not exporter.is_enabled()

    def test_export_event_skipped_when_disabled(self) -> None:
        exporter = OtelExporter(enabled=False)
        result = exporter.export_event("test.span", "hello")
        assert result.exported is False
        assert result.skipped_reason == "disabled"

    def test_export_event_no_raise_when_disabled(self) -> None:
        exporter = OtelExporter(enabled=False)
        # Must not raise regardless of inputs
        exporter.export_event("any.span", "any message", {"key": "val"})

    def test_export_event_skipped_when_tracer_is_none(self) -> None:
        exporter = OtelExporter(enabled=True, _tracer=None)
        result = exporter.export_event("span", "msg")
        assert result.exported is False
        assert result.skipped_reason == "disabled"


# ── missing OTel packages ─────────────────────────────────────────────────────

class TestMissingOtelPackages:
    def test_warning_emitted_when_sdk_missing(self) -> None:
        with _otel_env("http://localhost:4318"):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", False):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)

    def test_warning_text_does_not_contain_endpoint(self) -> None:
        secret_endpoint = "http://my-private-collector:4318/v1/traces"
        with _otel_env(secret_endpoint):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", False):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    OtelExporter.from_env()
        for w in caught:
            assert secret_endpoint not in str(w.message), (
                "Endpoint URL must not appear in warning text"
            )

    def test_returned_exporter_is_disabled_when_sdk_missing(self) -> None:
        with _otel_env("http://localhost:4318"):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", False):
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    exporter = OtelExporter.from_env()
        assert exporter.is_enabled() is False

    def test_warning_mentions_install_hint(self) -> None:
        with _otel_env("http://localhost:4318"):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", False):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    OtelExporter.from_env()
        msgs = " ".join(str(w.message) for w in caught)
        assert "opentelemetry" in msgs.lower()


# ── missing OTLP exporter package ────────────────────────────────────────────

class TestMissingOtlpExporterPackage:
    def test_disabled_when_otlp_exporter_missing(self) -> None:
        """If opentelemetry-api/sdk available but OTLP exporter not installed."""
        mock_provider = MagicMock()
        mock_tracer = MagicMock()
        mock_provider.get_tracer.return_value = mock_tracer

        with _otel_env("http://localhost:4318"):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", True):
                with patch("safecode.otel.exporter.OtelExporter._build_enabled") as mock_build:
                    mock_build.return_value = OtelExporter(enabled=False)
                    with warnings.catch_warnings(record=True):
                        warnings.simplefilter("always")
                        exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()


# ── successful initialisation (mock OTel) ─────────────────────────────────────

class TestSuccessfulInit:
    def _make_mock_tracer(self) -> MagicMock:
        """Build a mock tracer that supports the context-manager span protocol."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span
        return mock_tracer

    def test_enabled_with_mock_tracer(self) -> None:
        tracer = self._make_mock_tracer()
        exporter = OtelExporter(enabled=True, _tracer=tracer)
        assert exporter.is_enabled()

    def test_export_event_returns_exported_true(self) -> None:
        tracer = self._make_mock_tracer()
        exporter = OtelExporter(enabled=True, _tracer=tracer)
        result = exporter.export_event("agent.step", "Step 1 complete")
        assert result.exported is True
        assert result.skipped_reason is None

    def test_export_event_calls_start_span_with_name(self) -> None:
        tracer = self._make_mock_tracer()
        exporter = OtelExporter(enabled=True, _tracer=tracer)
        exporter.export_event("agent.step", "msg")
        tracer.start_as_current_span.assert_called_once_with("agent.step")

    def test_export_event_sets_message_attribute(self) -> None:
        tracer = self._make_mock_tracer()
        span = tracer.start_as_current_span.return_value.__enter__.return_value
        exporter = OtelExporter(enabled=True, _tracer=tracer)
        exporter.export_event("agent.step", "hello world")
        span.set_attribute.assert_any_call("safecode.message", "hello world")

    def test_export_event_sets_extra_attributes(self) -> None:
        tracer = self._make_mock_tracer()
        span = tracer.start_as_current_span.return_value.__enter__.return_value
        exporter = OtelExporter(enabled=True, _tracer=tracer)
        exporter.export_event("span", "msg", {"session_id": "abc123", "step": "1"})
        calls = [c[0] for c in span.set_attribute.call_args_list]
        assert ("session_id", "abc123") in calls
        assert ("step", "1") in calls

    def test_export_event_no_attributes_ok(self) -> None:
        tracer = self._make_mock_tracer()
        exporter = OtelExporter(enabled=True, _tracer=tracer)
        result = exporter.export_event("span", "msg", None)
        assert result.exported is True

    def test_from_env_builds_enabled_via_build_enabled(self) -> None:
        fake_exporter = OtelExporter(enabled=True, _tracer=MagicMock())
        with _otel_env("http://localhost:4318"):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", True):
                with patch.object(OtelExporter, "_build_enabled", return_value=fake_exporter):
                    result = OtelExporter.from_env()
        assert result.is_enabled()


# ── failure resilience ────────────────────────────────────────────────────────

class TestFailureResilience:
    def test_export_event_does_not_raise_on_tracer_exception(self) -> None:
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.side_effect = RuntimeError("boom")
        exporter = OtelExporter(enabled=True, _tracer=mock_tracer)
        result = exporter.export_event("span", "msg")  # must not raise
        assert result.exported is False
        assert result.skipped_reason is not None
        assert "export_error" in result.skipped_reason

    def test_export_event_warning_on_tracer_exception(self) -> None:
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.side_effect = RuntimeError("boom")
        exporter = OtelExporter(enabled=True, _tracer=mock_tracer)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            exporter.export_event("span", "msg")
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)

    def test_from_env_returns_disabled_on_build_exception(self) -> None:
        with _otel_env("http://localhost:4318"):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", True):
                with patch.object(OtelExporter, "_build_enabled", side_effect=RuntimeError("init fail")):
                    with warnings.catch_warnings(record=True):
                        warnings.simplefilter("always")
                        exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()

    def test_from_env_warning_on_build_exception_does_not_contain_endpoint(self) -> None:
        secret = "http://secret-collector:4318"
        with _otel_env(secret):
            with patch("safecode.otel.exporter._OTEL_SDK_AVAILABLE", True):
                with patch.object(OtelExporter, "_build_enabled", side_effect=RuntimeError("init fail")):
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        OtelExporter.from_env()
        for w in caught:
            assert secret not in str(w.message)


# ── OtelExportResult dataclass ────────────────────────────────────────────────

class TestOtelExportResult:
    def test_exported_true_no_reason(self) -> None:
        r = OtelExportResult(exported=True)
        assert r.exported is True
        assert r.skipped_reason is None

    def test_exported_false_with_reason(self) -> None:
        r = OtelExportResult(exported=False, skipped_reason="disabled")
        assert r.exported is False
        assert r.skipped_reason == "disabled"

    def test_frozen(self) -> None:
        r = OtelExportResult(exported=True)
        with pytest.raises((AttributeError, TypeError)):
            r.exported = False  # type: ignore[misc]


# ── no telemetry in test environment ─────────────────────────────────────────

class TestNoTelemetryByDefault:
    def test_otel_exporter_env_var_not_set_in_test_env(self) -> None:
        """SAFECODE_OTEL_EXPORTER must not be set in the test environment."""
        assert os.environ.get(_ENV_KEY, "") == "", (
            f"{_ENV_KEY} must not be set in test environment — "
            "tests must never emit real telemetry"
        )

    def test_from_env_is_disabled_in_test_env(self) -> None:
        exporter = OtelExporter.from_env()
        assert not exporter.is_enabled()
