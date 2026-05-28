"""Collect safe, bounded project context for the agent."""

from fnmatch import fnmatch
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.sandbox.filesystem import FilesystemBoundary


SKIP_DIRS = {".git", ".sac", ".venv", "__pycache__", ".pytest_cache"}
SKIP_FILES = {".DS_Store"}
SENSITIVE_NAMES = {".env", "id_rsa", "id_dsa", "credentials", "token"}
SENSITIVE_PATTERNS = {
    ".env*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_*",
    "*credential*",
    "*token*",
    "*secret*",
    "*password*",
}


class ContextCollector:
    """Read project metadata while avoiding sensitive files."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = config or SafeCodeConfig.load(project_root)
        self.filesystem = FilesystemBoundary(self.project_root, self.config)

    def collect(self) -> dict:
        """Return a small context dictionary for v0.1."""
        context = {
            "project_root": str(self.project_root),
            "files": self._list_files(),
            "readme": self._read_limited("README.md", self.config.max_file_lines),
            "pyproject": self._read_limited("pyproject.toml", self.config.max_file_lines),
        }
        return self._cap_context(context)

    def _list_files(self) -> list[str]:
        """Return a bounded, sorted file list relative to project_root."""
        files: list[str] = []

        for path in sorted(self.project_root.rglob("*")):
            relative = path.relative_to(self.project_root)

            if self._should_skip(relative):
                continue

            if path.is_symlink():
                continue

            if path.is_file():
                files.append(relative.as_posix())

            if len(files) >= self.config.max_tree_files:
                break

        return files

    def _read_limited(self, relative_path: str, max_lines: int) -> str | None:
        """Read at most max_lines from a UTF-8 text file."""
        relative = Path(relative_path)
        if self._should_skip(relative):
            return None

        path = self.project_root / relative
        if path.is_symlink() or not path.exists() or not path.is_file():
            return None
        try:
            self.filesystem.validate(path)
        except PermissionError:
            return None
        if path.stat().st_size > self.config.max_file_bytes:
            return None

        lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as file:
            for index, line in enumerate(file):
                if index >= max_lines:
                    break
                lines.append(line)
        return redact_secrets("".join(lines))

    def _should_skip(self, relative_path: Path) -> bool:
        """Skip generated, internal, and sensitive paths."""
        lowered_parts = {part.lower() for part in relative_path.parts}
        name = relative_path.name.lower()
        configured_sensitive = {item.lower() for item in self.config.sandbox.sensitive_names}

        if lowered_parts & SKIP_DIRS:
            return True
        if name in SKIP_FILES:
            return True
        if name in SENSITIVE_NAMES:
            return True
        if name in configured_sensitive or lowered_parts & configured_sensitive:
            return True
        if any(fnmatch(name, pattern) for pattern in SENSITIVE_PATTERNS):
            return True
        return False

    def _cap_context(self, context: dict) -> dict:
        """Keep string context under a global character budget."""
        remaining = self.config.max_context_chars
        capped: dict = {}
        for key, value in context.items():
            if isinstance(value, str):
                capped[key] = value[: max(remaining, 0)]
                remaining -= len(capped[key])
            else:
                capped[key] = value
        return capped
