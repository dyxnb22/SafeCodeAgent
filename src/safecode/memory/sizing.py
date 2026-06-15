"""Pure helper for computing .sac/ storage breakdown (experimental, v4.19.1)."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

_TMP_FILE_RE = re.compile(r"^\..+\.[0-9a-f]{32}\.tmp$")

_NAMED_SCOPES: list[tuple[str, str]] = [
    ("audit", "audit"),
    ("checkpoints", "checkpoints"),
    ("memory", "memory"),
    ("runtime_logs", "logs"),
    ("tasks", "tasks"),
]


class SacScopeEntry(BaseModel):
    name: str
    path_suffix: str
    bytes: int
    files: int


class SacSizeReport(BaseModel):
    root: str
    exists: bool
    total_bytes: int
    total_files: int
    scopes: list[SacScopeEntry]
    experimental: bool = True


def _walk_bytes_and_files(directory: Path) -> tuple[int, int]:
    """Recursively collect regular-file sizes; skip symlinks and temp files."""
    total_bytes = 0
    total_files = 0
    try:
        for entry in directory.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
                b, f = _walk_bytes_and_files(entry)
                total_bytes += b
                total_files += f
            elif entry.is_file():
                if _TMP_FILE_RE.match(entry.name):
                    continue
                try:
                    total_bytes += entry.stat().st_size
                    total_files += 1
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass
    return total_bytes, total_files


def compute_sac_size(project_root: Path) -> SacSizeReport:
    """Return a deterministic byte/file breakdown of .sac/ by named scope."""
    sac_root = project_root / ".sac"
    if not sac_root.exists():
        return SacSizeReport(
            root=str(sac_root),
            exists=False,
            total_bytes=0,
            total_files=0,
            scopes=[],
        )

    total_bytes, total_files = _walk_bytes_and_files(sac_root)

    scope_entries: list[SacScopeEntry] = []
    accounted_bytes = 0
    accounted_files = 0

    for scope_name, path_suffix in _NAMED_SCOPES:
        scope_dir = sac_root / path_suffix
        if scope_dir.exists():
            b, f = _walk_bytes_and_files(scope_dir)
        else:
            b, f = 0, 0
        scope_entries.append(SacScopeEntry(
            name=scope_name,
            path_suffix=f".sac/{path_suffix}/",
            bytes=b,
            files=f,
        ))
        accounted_bytes += b
        accounted_files += f

    other_bytes = total_bytes - accounted_bytes
    other_files = total_files - accounted_files
    scope_entries.append(SacScopeEntry(
        name="other",
        path_suffix=".sac/",
        bytes=max(other_bytes, 0),
        files=max(other_files, 0),
    ))

    scope_entries.sort(key=lambda e: e.name)

    return SacSizeReport(
        root=str(sac_root),
        exists=True,
        total_bytes=total_bytes,
        total_files=total_files,
        scopes=scope_entries,
    )
