"""Optional OpenTelemetry integration for SafeCode Agent (v3.6.2, experimental)."""

from safecode.otel.exporter import OtelExportResult, OtelExporter

__all__ = ["OtelExporter", "OtelExportResult"]
