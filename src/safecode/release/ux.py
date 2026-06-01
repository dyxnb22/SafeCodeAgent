"""Shared release command rendering helpers."""

from __future__ import annotations


def status_label(ok: bool) -> str:
    """Return the canonical release command status label."""
    return "PASS" if ok else "FAIL"


def exit_code(ok: bool) -> int:
    """Return the canonical release command process exit code."""
    return 0 if ok else 1


def header(title: str, ok: bool) -> list[str]:
    """Return a standard release command header."""
    return [
        title,
        "=" * len(title),
        f"Status: {status_label(ok)}",
        "",
    ]


def next_steps(steps: list[str], *, ok_message: str = "No next steps.") -> list[str]:
    """Render next steps with a consistent heading."""
    lines = ["Next steps:"]
    if steps:
        lines.extend(f"  {step}" for step in steps)
    else:
        lines.append(f"  {ok_message}")
    return lines
