"""Collect safe, bounded project context for the agent."""

from pathlib import Path

from safecode.config import SafeCodeConfig


SKIP_DIRS = {".git", ".sac", ".venv", "__pycache__", ".pytest_cache"}
SKIP_FILES = {".DS_Store"}
SENSITIVE_NAMES = {".env", "id_rsa", "id_dsa", "credentials", "token"}


class ContextCollector:
    """Read project metadata while avoiding sensitive files."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig()

    def collect(self) -> dict:
        """Return a small context dictionary for v0.1."""
        return {
            "project_root": str(self.project_root),
            "files": self._list_files(),
            "readme": self._read_limited("README.md", self.config.max_file_lines),
            "pyproject": self._read_limited("pyproject.toml", self.config.max_file_lines),
        }

    def _list_files(self) -> list[str]:
        """Return a bounded, sorted file list relative to project_root."""
        files: list[str] = []

        for path in sorted(self.project_root.rglob("*")):
            relative = path.relative_to(self.project_root)

            if self._should_skip(relative):
                continue

            if path.is_file():
                files.append(relative.as_posix())

            if len(files) >= self.config.max_tree_files:
                break

        return files

    def _read_limited(self, relative_path: str, max_lines: int) -> str | None:
        """Read at most max_lines from a UTF-8 text file."""
        path = self.project_root / relative_path
        if not path.exists() or not path.is_file():
            return None

        lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as file:
            for index, line in enumerate(file):
                if index >= max_lines:
                    break
                lines.append(line)
        return "".join(lines)

    def _should_skip(self, relative_path: Path) -> bool:
        """Skip generated, internal, and sensitive paths."""
        parts = set(relative_path.parts)
        name = relative_path.name

        if parts & SKIP_DIRS:
            return True
        if name in SKIP_FILES:
            return True
        if name in SENSITIVE_NAMES:
            return True
        return False
