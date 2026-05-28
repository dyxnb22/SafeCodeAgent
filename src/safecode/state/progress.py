"""Progress file management for long-running tasks."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProgressState:
    """A small structured view of .sac/progress.md."""

    goal: str
    completed: list[str]
    next_steps: list[str]
    blockers: list[str]


class ProgressStore:
    """Persist progress in a human-readable Markdown file."""

    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".sac" / "progress.md"

    def ensure(self) -> Path:
        """Create an empty progress file if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(ProgressState(goal="", completed=[], next_steps=[], blockers=[]))
        return self.path

    def write(self, state: ProgressState) -> None:
        """Write progress as simple Markdown."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = ["# SafeCode Progress", "", "## Goal", state.goal or "(empty)", ""]
        text.extend(["## Completed", *[f"- {item}" for item in state.completed], ""])
        text.extend(["## Next Steps", *[f"- {item}" for item in state.next_steps], ""])
        text.extend(["## Blockers", *[f"- {item}" for item in state.blockers], ""])
        self.path.write_text("\n".join(text), encoding="utf-8")

    def read_text(self) -> str:
        """Read raw progress Markdown."""
        self.ensure()
        return self.path.read_text(encoding="utf-8")
