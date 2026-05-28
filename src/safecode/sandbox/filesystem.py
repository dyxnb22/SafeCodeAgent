"""Filesystem containment checks."""

from pathlib import Path

from safecode.config import SafeCodeConfig


class FilesystemBoundary:
    """Validate paths before file operations."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = config or SafeCodeConfig.load(project_root)

    def validate(self, path: Path) -> Path:
        """Return resolved path when it is allowed."""
        resolved = path.resolve()
        if self.config.sandbox.restrict_to_project_root and not self._inside_project(resolved):
            raise PermissionError(f"Path escapes project root: {path}")
        parts = {part.lower() for part in resolved.parts}
        blocked = {name.lower() for name in self.config.sandbox.sensitive_names}
        if parts & blocked:
            raise PermissionError(f"Refusing sensitive path: {path}")
        return resolved

    def _inside_project(self, path: Path) -> bool:
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False
