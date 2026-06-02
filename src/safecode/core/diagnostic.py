"""Typed diagnostic substrate for doctor/release/policy checks.

A `Diagnostic` is a single named check result with a canonical status, a
human-readable message, optional next-step hints, and optional metadata.
A `DiagnosticGroup` aggregates many diagnostics under a single label and
exposes aggregate status, pass/fail booleans, and renderer-friendly output.

The substrate is pure and free of CLI rendering concerns. Callers may map
their existing dataclasses to/from Diagnostic without changing user-facing
output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class DiagnosticStatus(str, Enum):
    """Canonical status values used across doctor/release diagnostics."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


# Worst-case ordering for aggregation. Higher value means more severe.
# FAIL > WARN > SKIP > PASS. SKIP is not failure but stronger than PASS for
# rendering purposes — it signals that the check did not run.
_STATUS_SEVERITY: dict[DiagnosticStatus, int] = {
    DiagnosticStatus.PASS: 0,
    DiagnosticStatus.SKIP: 1,
    DiagnosticStatus.WARN: 2,
    DiagnosticStatus.FAIL: 3,
}


@dataclass(frozen=True)
class Diagnostic:
    """One typed diagnostic result.

    Attributes:
        name: stable identifier for the check (e.g., "release_version").
        status: canonical PASS/FAIL/WARN/SKIP status.
        message: short human-readable detail.
        hints: optional list of next-step hints (e.g., commands).
        metadata: optional structured metadata for renderers.
    """

    name: str
    status: DiagnosticStatus
    message: str = ""
    hints: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Diagnostic.name must be a non-empty string")
        if not isinstance(self.status, DiagnosticStatus):
            raise TypeError("Diagnostic.status must be a DiagnosticStatus")
        # Normalise hints to a tuple of strings regardless of input shape.
        # We accept list/tuple/iterable inputs for ergonomics.
        if not isinstance(self.hints, tuple):
            object.__setattr__(self, "hints", tuple(self.hints))
        for hint in self.hints:
            if not isinstance(hint, str):
                raise TypeError("Diagnostic.hints must contain strings")

    @property
    def passed(self) -> bool:
        """True only when the diagnostic is PASS."""
        return self.status is DiagnosticStatus.PASS

    @property
    def failed(self) -> bool:
        """True only when the diagnostic is FAIL."""
        return self.status is DiagnosticStatus.FAIL

    @classmethod
    def from_bool(
        cls,
        name: str,
        ok: bool,
        message: str = "",
        *,
        hints: Iterable[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> "Diagnostic":
        """Build a Diagnostic from a legacy boolean check."""
        status = DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL
        return cls(
            name=name,
            status=status,
            message=message,
            hints=tuple(hints),
            metadata=dict(metadata) if metadata else {},
        )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "hints": list(self.hints),
            "metadata": dict(self.metadata),
        }

    def render_line(self) -> str:
        """One-line renderer-friendly output."""
        return f"[{self.status.value}] {self.name}: {self.message}".rstrip(": ").rstrip()


@dataclass(frozen=True)
class DiagnosticGroup:
    """Aggregates a list of diagnostics under one label."""

    name: str
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("DiagnosticGroup.name must be a non-empty string")
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diag in self.diagnostics:
            if not isinstance(diag, Diagnostic):
                raise TypeError("DiagnosticGroup.diagnostics must contain Diagnostic")

    @property
    def status(self) -> DiagnosticStatus:
        """Aggregate status — worst severity among the diagnostics."""
        return aggregate_status(self.diagnostics)

    @property
    def passed(self) -> bool:
        """True only if every diagnostic is PASS (empty group passes)."""
        return all_passed(self.diagnostics)

    @property
    def failed_diagnostics(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.status is DiagnosticStatus.FAIL)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.status is DiagnosticStatus.WARN)

    @property
    def skipped(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.status is DiagnosticStatus.SKIP)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "status": self.status.value,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }

    def render_lines(self) -> list[str]:
        """Renderer-friendly multi-line output."""
        return [d.render_line() for d in self.diagnostics]


def aggregate_status(diagnostics: Iterable[Diagnostic]) -> DiagnosticStatus:
    """Return the worst status among the diagnostics.

    Severity order (low to high): PASS < SKIP < WARN < FAIL.
    An empty input is treated as PASS.
    """
    severity = -1
    worst = DiagnosticStatus.PASS
    for diag in diagnostics:
        diag_severity = _STATUS_SEVERITY[diag.status]
        if diag_severity > severity:
            severity = diag_severity
            worst = diag.status
    return worst


def all_passed(diagnostics: Iterable[Diagnostic]) -> bool:
    """True only when every diagnostic is PASS. Empty input passes."""
    return all(d.status is DiagnosticStatus.PASS for d in diagnostics)
