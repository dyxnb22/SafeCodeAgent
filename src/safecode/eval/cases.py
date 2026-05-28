"""Local evaluation cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    """One deterministic eval case."""

    name: str
    command: str
    expected_text: str


def default_cases() -> list[EvalCase]:
    """Return lightweight demo cases."""
    return [
        EvalCase("help", "uv run sac --help", "SafeCode Agent"),
        EvalCase("history", "uv run sac history", "SafeCode"),
    ]
