"""Minimal IDE bridge for opening SafeCode context (v2.3.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.context.selector import ContextSelector
from safecode.index.files import FileIndexer
from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchProposal
from safecode.sandbox.filesystem import FilesystemBoundary


@dataclass(frozen=True)
class IDEOpenTarget:
    """One path/URI an editor can open."""

    label: str
    path: Path
    uri: str


def pending_diff_target(project_root: Path) -> IDEOpenTarget:
    """Materialize the current pending patch diff for IDE display."""
    pending_path = project_root / ".sac" / "pending_patch.json"
    if not pending_path.exists() or pending_path.is_symlink():
        raise FileNotFoundError("No pending patch found.")

    proposal = PatchProposal.model_validate_json(pending_path.read_text(encoding="utf-8"))
    diff_text = build_unified_diff(project_root, proposal)
    output_path = project_root / ".sac" / "ide" / "pending.diff"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(diff_text, encoding="utf-8")
    return _target("pending diff", output_path)


def selected_file_targets(project_root: Path, query: str, *, limit: int = 5) -> list[IDEOpenTarget]:
    """Return safe selected files for an editor to open."""
    boundary = FilesystemBoundary(project_root)
    targets: list[IDEOpenTarget] = []
    for source in ContextSelector(project_root).select_sources(query, limit=limit):
        path = (project_root / source.path).resolve()
        try:
            boundary.validate(path)
        except PermissionError:
            continue
        if path.exists() and path.is_file() and not path.is_symlink():
            targets.append(_target(source.reason, path))
    if not targets:
        targets.extend(_fallback_file_targets(project_root, query, boundary, limit))
    return targets


def _fallback_file_targets(project_root: Path, query: str, boundary: FilesystemBoundary, limit: int) -> list[IDEOpenTarget]:
    tokens = {part.lower() for part in query.replace("/", " ").replace("_", " ").split() if part}
    if not tokens:
        return []
    targets: list[IDEOpenTarget] = []
    for item in FileIndexer(project_root).index():
        path = (project_root / item.path).resolve()
        try:
            boundary.validate(path)
        except PermissionError:
            continue
        if not path.exists() or not path.is_file() or path.is_symlink():
            continue
        path_text = item.path.lower()
        matched_path = any(token in path_text for token in tokens)
        matched_content = False
        if not matched_path and path.stat().st_size <= 64_000:
            try:
                sample = path.read_text(encoding="utf-8", errors="replace")[:8192].lower()
                matched_content = any(token in sample for token in tokens)
            except OSError:
                matched_content = False
        if matched_path or matched_content:
            label = "path/content matched" if matched_content else "path matched"
            targets.append(_target(label, path))
        if len(targets) >= limit:
            break
    return targets


def _target(label: str, path: Path) -> IDEOpenTarget:
    resolved = path.resolve()
    return IDEOpenTarget(label=label, path=resolved, uri=resolved.as_uri())
