"""Failure taxonomy for task eval replay results (v2.5.2).

Provides a small, stable set of failure categories, a typed ``ClassifiedFailure``
dataclass, and ``classify_replay_result`` which maps the structured signals in a
``ReplayResult`` to a list of ``ClassifiedFailure`` objects.

Classification rules (in priority order):
1. Structured violation fields (``forbidden_file_writes_violated``,
   ``forbidden_commands_violated``) are processed first — no string parsing needed.
2. Workspace/setup errors (``result.error``) classify the whole result.
3. Remaining failure_reasons are categorised by known keyword patterns that
   match the prefixes the runner produces — NOT by matching exact full strings.
4. Anything unrecognised falls into ``FailureCategory.unknown``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safecode.eval.runner import ReplayResult


class FailureCategory(StrEnum):
    """Stable taxonomy of eval / replay failure kinds."""

    context_miss = "context_miss"
    patch_parse = "patch_parse"
    validation = "validation"
    command_blocked = "command_blocked"
    forbidden_file_write = "forbidden_file_write"
    forbidden_file_changed = "forbidden_file_changed"
    setup = "setup"
    timeout = "timeout"
    model_error = "model_error"
    audit_unverified = "audit_unverified"
    unknown = "unknown"


@dataclass(frozen=True)
class ClassifiedFailure:
    """A single classified failure from a replay result.

    ``category`` is the stable taxonomy value.
    ``reason`` is a human-readable summary (safe to display in reports).
    ``detail`` carries the matched pattern or filename when derived from a
    structured signal, ``None`` otherwise.
    """

    category: FailureCategory
    reason: str
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "reason": self.reason,
            "detail": self.detail,
        }


# ── Public classifier ──────────────────────────────────────────────────────


def classify_replay_result(result: "ReplayResult") -> list[ClassifiedFailure]:
    """Return a list of ``ClassifiedFailure`` objects for a ``ReplayResult``.

    Deterministic: given the same ``ReplayResult`` the output is always the
    same.  Prefers structured fields over string-matching when both are
    available.  Returns ``[]`` when ``result.passed is True``.
    """
    if result.passed:
        return []

    failures: list[ClassifiedFailure] = []

    # ── Workspace / setup error (short-circuit) ────────────────────────────
    if result.error is not None:
        failures.append(ClassifiedFailure(
            category=FailureCategory.setup,
            reason=result.error,
            detail=None,
        ))
        return failures

    # ── Structured signals ─────────────────────────────────────────────────
    for pattern in result.forbidden_file_writes_violated:
        failures.append(ClassifiedFailure(
            category=FailureCategory.forbidden_file_write,
            reason=f"Forbidden file write detected: {pattern!r}",
            detail=pattern,
        ))

    for pattern in result.forbidden_commands_violated:
        failures.append(ClassifiedFailure(
            category=FailureCategory.command_blocked,
            reason=f"Forbidden command pattern observed: {pattern!r}",
            detail=pattern,
        ))

    # ── Remaining failure_reasons ──────────────────────────────────────────
    # Skip reasons already covered by the structured signals above.
    _structured_prefixes = (
        "Safety violation: forbidden file write",
        "Safety violation: forbidden command",
    )

    for reason in result.failure_reasons:
        if any(reason.startswith(prefix) for prefix in _structured_prefixes):
            continue
        failures.append(ClassifiedFailure(
            category=_categorize_reason(reason),
            reason=reason,
            detail=None,
        ))

    return failures


# ── Internal ───────────────────────────────────────────────────────────────


def _categorize_reason(reason: str) -> FailureCategory:
    """Map a single failure reason string to a ``FailureCategory``.

    Matches on known keyword prefixes produced by the replay runner, not on
    exact full strings.  Order matters: more-specific checks come first.
    """
    # Setup-phase failures (check before generic "timed out")
    if "Setup command" in reason or "Workspace materialisation" in reason:
        return FailureCategory.setup

    # Timeout (validation-phase commands that stall)
    if "timed out" in reason.lower():
        return FailureCategory.timeout

    # Forbidden file changed (fixture-level forbidden_changed_files)
    if "Forbidden file" in reason and "changed" in reason:
        return FailureCategory.forbidden_file_changed

    # Validation constraint failures
    if any(kw in reason for kw in (
        "Validation command",
        "Expected last validation command",
        "Expected output to contain",
        "Expected workspace diff to contain",
        "Expected file",
        "Expected changed file",
    )):
        return FailureCategory.validation

    return FailureCategory.unknown
