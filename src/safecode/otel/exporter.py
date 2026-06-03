"""Optional OpenTelemetry exporter for runtime events and agent steps (v3.6.2).

Disabled by default.  Enable via ``SAFECODE_OTEL_EXPORTER=<otlp_endpoint>``.

Safety invariants:
- No telemetry is emitted unless SAFECODE_OTEL_EXPORTER is explicitly set.
- Missing opentelemetry packages → RuntimeWarning + disabled (fail closed).
- Endpoint string is never written to error text, logs, or diagnostic messages.
- ``export_event()`` never raises; failures return an OtelExportResult with
  ``exported=False`` and a ``skipped_reason`` string.
- OTel remains experimental; this module does not change audit/journal behavior.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

_ENV_KEY = "SAFECODE_OTEL_EXPORTER"

# Attempt a module-level import probe so tests can patch it without side effects.
_OTEL_SDK_AVAILABLE: bool
try:
    import opentelemetry  # type: ignore[import]  # noqa: F401
    _OTEL_SDK_AVAILABLE = True
except ImportError:
    _OTEL_SDK_AVAILABLE = False


@dataclass(frozen=True)
class OtelExportResult:
    """Outcome of a single ``export_event`` call."""

    exported: bool
    skipped_reason: str | None = None


class OtelExporter:
    """Optional OpenTelemetry exporter for SafeCode runtime events.

    Construct with ``OtelExporter.from_env()``; the result is always safe to
    call even when OTel is unavailable or the env var is absent.

    This class is intentionally a thin adapter so tests can inject a fake tracer
    without importing the real OTel SDK.
    """

    def __init__(self, *, enabled: bool = False, _tracer: object = None) -> None:
        self._enabled = enabled
        self._tracer = _tracer

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "OtelExporter":
        """Build an exporter from ``SAFECODE_OTEL_EXPORTER``.

        Returns a disabled no-op exporter when the env var is absent or empty.
        Issues a ``RuntimeWarning`` and returns disabled when the OTel packages
        are missing — the caller does not need to handle ImportError.
        """
        endpoint = os.environ.get(_ENV_KEY, "").strip()
        if not endpoint:
            return cls(enabled=False)

        if not _OTEL_SDK_AVAILABLE:
            warnings.warn(
                f"{_ENV_KEY} is set but the 'opentelemetry-api' and "
                "'opentelemetry-sdk' packages are not installed. "
                "No telemetry will be exported. "
                "Install optional OTel packages: "
                "pip install opentelemetry-api opentelemetry-sdk "
                "opentelemetry-exporter-otlp-proto-http",
                RuntimeWarning,
                stacklevel=2,
            )
            return cls(enabled=False)

        try:
            return cls._build_enabled(endpoint)
        except Exception as exc:
            warnings.warn(
                f"Failed to initialise OTel exporter: {type(exc).__name__}. "
                "No telemetry will be exported.",
                RuntimeWarning,
                stacklevel=2,
            )
            return cls(enabled=False)

    @classmethod
    def _build_enabled(cls, endpoint: str) -> "OtelExporter":
        """Build a tracer provider with an OTLP span exporter.

        Called only when the opentelemetry-api/sdk are available.
        """
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import]

        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import]
                OTLPSpanExporter,
            )
        except ImportError:
            warnings.warn(
                "The 'opentelemetry-exporter-otlp-proto-http' package is not installed. "
                "No telemetry will be exported. "
                "pip install opentelemetry-exporter-otlp-proto-http",
                RuntimeWarning,
                stacklevel=3,
            )
            return cls(enabled=False)

        provider = TracerProvider()
        span_exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        tracer = provider.get_tracer("safecode-agent")
        return cls(enabled=True, _tracer=tracer)

    # ── Public API ────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True only when telemetry will actually be sent."""
        return self._enabled

    def export_event(
        self,
        span_name: str,
        message: str,
        attributes: dict[str, str] | None = None,
    ) -> OtelExportResult:
        """Record one runtime event as an OTel span.

        Safe to call unconditionally — returns ``OtelExportResult(exported=False)``
        when the exporter is disabled or the OTel call fails.  Never raises.

        ``message`` is attached as the ``safecode.message`` span attribute.
        ``attributes`` values are coerced to ``str`` before being set.
        """
        if not self._enabled or self._tracer is None:
            return OtelExportResult(exported=False, skipped_reason="disabled")

        try:
            with self._tracer.start_as_current_span(span_name) as span:  # type: ignore[union-attr]
                span.set_attribute("safecode.message", message)
                if attributes:
                    for key, val in attributes.items():
                        span.set_attribute(key, str(val))
            return OtelExportResult(exported=True)
        except Exception as exc:
            warnings.warn(
                f"OTel export failed for span {span_name!r}: {type(exc).__name__}",
                RuntimeWarning,
                stacklevel=2,
            )
            return OtelExportResult(
                exported=False,
                skipped_reason=f"export_error:{type(exc).__name__}",
            )
