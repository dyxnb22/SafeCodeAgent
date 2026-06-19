"""Optional OpenTelemetry-style span export behind the trace emitter (v2.5.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from safecode.enterprise.api.exceptions import SettingsValidationError
from safecode.enterprise.trace.events import TraceEvent


@dataclass(frozen=True)
class OtelSpanRecord:
    """Redacted span snapshot suitable for export."""

    name: str
    run_id: str
    tenant_id: str
    service_name: str
    event_id: str
    event_type: str
    attributes: dict[str, str]


@runtime_checkable
class OtelExporter(Protocol):
    """Parallel trace export hook; must not replace local trace files."""

    def export_span(self, span: OtelSpanRecord) -> None: ...


@dataclass
class InMemoryOtelExporter:
    """Deterministic fake collector for offline tests."""

    spans: list[OtelSpanRecord] = field(default_factory=list)
    fail_on_export: bool = False

    def export_span(self, span: OtelSpanRecord) -> None:
        if self.fail_on_export:
            raise RuntimeError("otel export failed")
        self.spans.append(span)


@dataclass(frozen=True)
class OtelExportConfig:
    enabled: bool = False
    endpoint: str | None = None
    service_name: str = "safecode-enterprise"


def parse_otel_enabled(raw: str | bool | None) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise SettingsValidationError(f"invalid OTEL enabled value: {raw!r}")


def validate_otel_config(config: OtelExportConfig) -> OtelExportConfig:
    if not config.enabled:
        return config
    if not config.service_name.strip():
        raise SettingsValidationError("otel service name must not be blank when export is enabled")
    if not config.endpoint or not config.endpoint.strip():
        raise SettingsValidationError("otel endpoint is required when export is enabled")
    return config


def span_from_trace_event(event: TraceEvent, *, service_name: str) -> OtelSpanRecord:
    attributes: dict[str, str] = {
        "node_id": event.node_id,
        "seq": str(event.seq),
    }
    if event.actor_id:
        attributes["actor_id"] = event.actor_id
    if event.policy_snapshot_id:
        attributes["policy_snapshot_id"] = event.policy_snapshot_id
    for key, value in event.payload.items():
        if isinstance(value, (str, int, float, bool)):
            attributes[f"payload.{key}"] = str(value)
    return OtelSpanRecord(
        name=f"trace.{event.type.value}",
        run_id=event.run_id,
        tenant_id=event.tenant_id,
        service_name=service_name,
        event_id=event.event_id,
        event_type=event.type.value,
        attributes=attributes,
    )


def build_otel_exporter(config: OtelExportConfig) -> OtelExporter | None:
    validated = validate_otel_config(config)
    if not validated.enabled:
        return None
    return RecordingOtelExporter(
        endpoint=validated.endpoint or "",
        service_name=validated.service_name,
    )


@dataclass
class RecordingOtelExporter:
    """Records exported spans locally; endpoint is validated but not contacted in tests."""

    endpoint: str
    service_name: str
    spans: list[OtelSpanRecord] = field(default_factory=list)
    fail_on_export: bool = False

    def export_span(self, span: OtelSpanRecord) -> None:
        if self.fail_on_export:
            raise RuntimeError("otel export failed")
        if not self.endpoint.strip():
            raise SettingsValidationError("otel endpoint must not be blank")
        self.spans.append(span)
