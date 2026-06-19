"""File-backed trace event emitter."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from safecode.enterprise.trace.otel_exporter import OtelExporter, span_from_trace_event
from safecode.enterprise.trace.redaction import (
    DEFAULT_TRACE_EXPORT_PROFILE,
    apply_profile_to_payload,
)
from safecode.enterprise.trace.events import (
    MAX_PAYLOAD_FIELD_BYTES,
    TraceEvent,
    TraceEventType,
    make_event_id,
    utc_now_iso,
)
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.exceptions import InvalidRunIdError
from safecode.enterprise.workflow.ids import validate_run_id


def trace_file_path(sac_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    root = (sac_root / "enterprise" / "runs").resolve()
    target = (root / run_id).resolve()
    if target.parent != root:
        raise InvalidRunIdError(f"run path escapes runs root: {run_id!r}")
    return target / "trace.jsonl"


def redact_event_payload(payload: dict[str, object]) -> tuple[dict[str, object], bool, str | None]:
    redacted, applied = apply_profile_to_payload(
        payload,
        profile=DEFAULT_TRACE_EXPORT_PROFILE,
    )
    reason = "profile_strict" if applied else None
    return redacted, applied, reason


def _atomic_append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".append.tmp")
    payload = line if line.endswith("\n") else f"{line}\n"
    tmp_path.write_text(payload, encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(tmp_path.read_text(encoding="utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.unlink(missing_ok=True)


def _load_max_seq(path: Path) -> int:
    if not path.is_file():
        return 0
    max_seq = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        seq = record.get("seq")
        if isinstance(seq, int):
            max_seq = max(max_seq, seq)
    return max_seq


def _load_event_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        event_id = record.get("event_id")
        if isinstance(event_id, str):
            seen.add(event_id)
    return seen


class TraceEmitter:
    """Append-only JSONL emitter with idempotent event_id handling."""

    def __init__(
        self,
        sac_root: Path,
        run_id: str,
        *,
        otel_exporter: OtelExporter | None = None,
        otel_service_name: str = "safecode-enterprise",
    ) -> None:
        validate_run_id(run_id)
        self.sac_root = sac_root
        self.run_id = run_id
        self._path = trace_file_path(sac_root, run_id)
        self._seen_ids = _load_event_ids(self._path)
        self._next_seq = _load_max_seq(self._path) + 1
        self._otel_exporter = otel_exporter
        self._otel_service_name = otel_service_name

    def allocate_seq(self) -> int:
        seq = self._next_seq
        self._next_seq += 1
        return seq

    @property
    def path(self) -> Path:
        return self._path

    def has_event(self, event_id: str) -> bool:
        return event_id in self._seen_ids

    def emit(
        self,
        event_type: TraceEventType | str,
        *,
        node_id: str,
        seq: int,
        tenant_id: str,
        payload: dict[str, object] | None = None,
        actor_id: str | None = None,
        policy_snapshot_id: str | None = None,
        cost: NodeCost | None = None,
        duration_ms: int | None = None,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> TraceEvent | None:
        resolved_type = (
            event_type if isinstance(event_type, TraceEventType) else TraceEventType(event_type)
        )
        resolved_event_id = event_id or make_event_id(
            run_id=self.run_id,
            node_id=node_id,
            seq=seq,
        )
        if resolved_event_id in self._seen_ids:
            return None
        redacted_payload, redaction_applied, redaction_reason = redact_event_payload(
            dict(payload or {})
        )
        event = TraceEvent(
            event_id=resolved_event_id,
            run_id=self.run_id,
            tenant_id=tenant_id,
            node_id=node_id,
            seq=seq,
            type=resolved_type,
            timestamp=timestamp or utc_now_iso(),
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload=redacted_payload,  # type: ignore[arg-type]
            redaction_applied=redaction_applied,
            redaction_reason=redaction_reason,
            cost=cost,
            duration_ms=duration_ms,
        )
        _atomic_append_line(self._path, event.model_dump_json())
        self._seen_ids.add(resolved_event_id)
        if self._otel_exporter is not None:
            try:
                self._otel_exporter.export_span(
                    span_from_trace_event(event, service_name=self._otel_service_name)
                )
            except Exception:
                pass
        return event

    def iter_events(self) -> list[TraceEvent]:
        if not self._path.is_file():
            return []
        events: list[TraceEvent] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(TraceEvent.model_validate_json(line))
        return events

    def event_ids(self) -> Iterable[str]:
        return tuple(self._seen_ids)
