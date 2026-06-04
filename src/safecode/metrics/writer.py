"""Optional live-session metrics writer for v3.10.0.

Writes JSONL records to ``.sac/metrics.jsonl`` when enabled.

Opt-in only — disabled by default. Enable via:
  - ``SAFECODE_METRICS=1`` environment variable, or
  - ``metrics_enabled = true`` in ``.sac/config.toml``.

Design invariants:
- Never raises into the caller's workflow (all errors are silently swallowed).
- Size-bounded per session: stops writing after ``_MAX_SESSION_BYTES``.
- Redacts sensitive content before writing.
- Captures: step start/end, tool intent, pending patch size, retry count.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.context.redactor import redact_secrets
from safecode.utils.time import utc_now_iso

# Max bytes written per session before the writer stops silently.
_MAX_SESSION_BYTES = 1 * 1024 * 1024  # 1 MiB

_METRICS_FILENAME = "metrics.jsonl"
_ENV_KEY = "SAFECODE_METRICS"


def _metrics_enabled() -> bool:
    return os.environ.get(_ENV_KEY, "").strip() == "1"


@dataclass
class MetricsEvent:
    """One live-session metrics event (JSONL record)."""

    event_type: str
    session_id: str
    step: int | None = None
    tool_intent: str | None = None
    pending_patch_size: int | None = None
    retry_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "ts": utc_now_iso(),
        }
        if self.step is not None:
            data["step"] = self.step
        if self.tool_intent is not None:
            data["tool_intent"] = self.tool_intent
        if self.pending_patch_size is not None:
            data["pending_patch_size"] = self.pending_patch_size
        if self.retry_count is not None:
            data["retry_count"] = self.retry_count
        if self.extra:
            data["extra"] = self.extra
        return data


class MetricsWriter:
    """Write live-session metrics to ``.sac/metrics.jsonl``.

    Instantiate once per session. Call ``write_event()`` to append records.
    All errors are swallowed — never raises into the caller.

    When disabled (default), all writes are no-ops.
    """

    def __init__(
        self,
        project_root: Path,
        session_id: str,
        *,
        enabled: bool | None = None,
        max_bytes: int = _MAX_SESSION_BYTES,
    ) -> None:
        self._project_root = project_root
        self._session_id = session_id
        self._max_bytes = max_bytes
        self._bytes_written = 0
        self._enabled = enabled if enabled is not None else _metrics_enabled()
        self._path: Path | None = None
        if self._enabled:
            try:
                sac_dir = project_root / ".sac"
                sac_dir.mkdir(parents=True, exist_ok=True)
                self._path = sac_dir / _METRICS_FILENAME
            except Exception:
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def path(self) -> Path | None:
        return self._path

    def write_event(self, event: MetricsEvent) -> None:
        """Append one event as a JSONL record. Never raises."""
        if not self._enabled or self._path is None:
            return
        if self._bytes_written >= self._max_bytes:
            return
        try:
            raw = json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True)
            line = raw + "\n"
            encoded = line.encode("utf-8")
            if self._bytes_written + len(encoded) > self._max_bytes:
                return
            with self._path.open("ab") as fh:
                fh.write(encoded)
            self._bytes_written += len(encoded)
        except Exception:
            pass

    def record_step_start(self, step: int, tool_intent: str | None = None) -> None:
        """Record step start event."""
        self.write_event(MetricsEvent(
            event_type="step_start",
            session_id=self._session_id,
            step=step,
            tool_intent=tool_intent,
        ))

    def record_step_end(self, step: int, tool_intent: str | None = None) -> None:
        """Record step end event."""
        self.write_event(MetricsEvent(
            event_type="step_end",
            session_id=self._session_id,
            step=step,
            tool_intent=tool_intent,
        ))

    def record_pending_patch(self, step: int, patch_text: str) -> None:
        """Record pending patch size (text is not stored; only byte count)."""
        try:
            size = len(patch_text.encode("utf-8"))
        except Exception:
            size = 0
        self.write_event(MetricsEvent(
            event_type="pending_patch",
            session_id=self._session_id,
            step=step,
            pending_patch_size=size,
        ))

    def record_retry(self, step: int, retry_count: int) -> None:
        """Record a retry event."""
        self.write_event(MetricsEvent(
            event_type="retry",
            session_id=self._session_id,
            step=step,
            retry_count=retry_count,
        ))


def make_metrics_writer(
    project_root: Path,
    session_id: str,
    *,
    enabled: bool | None = None,
) -> MetricsWriter:
    """Factory that never raises. Returns a disabled writer on any error."""
    try:
        return MetricsWriter(project_root, session_id, enabled=enabled)
    except Exception:
        w = object.__new__(MetricsWriter)
        w._enabled = False
        w._path = None
        w._bytes_written = 0
        w._max_bytes = _MAX_SESSION_BYTES
        w._project_root = project_root
        w._session_id = session_id
        return w  # type: ignore[return-value]
