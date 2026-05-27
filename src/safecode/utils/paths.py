"""Path helpers for keeping file access inside the project root."""

from pathlib import Path


def resolve_inside_root(project_root: Path, relative_path: Path) -> Path:
    """Resolve a path and ensure future code can reject root escapes."""
    return (project_root / relative_path).resolve()
