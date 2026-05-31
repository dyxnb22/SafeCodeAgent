"""Path helpers for keeping file access inside the project root."""

from pathlib import Path


def resolve_inside_root(project_root: Path, relative_path: Path) -> Path:
    """Resolve a path and reject paths outside the project root."""
    root = project_root.resolve()
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Path escapes project root: {relative_path}") from exc
    return resolved
