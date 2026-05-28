"""Read user-authored project rules from SAC.md."""

from pathlib import Path


DEFAULT_RULES = """# SafeCode Project Rules

- Show diffs before applying file changes.
- Create checkpoints before writes.
- Keep generated changes small and reviewable.
"""


class ProjectRules:
    """Access project rules."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.path = project_root / "SAC.md"

    def ensure(self) -> Path:
        """Create SAC.md if it does not exist."""
        if not self.path.exists():
            self.path.write_text(DEFAULT_RULES, encoding="utf-8")
        return self.path

    def read(self) -> str:
        """Read SAC.md when present."""
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")
