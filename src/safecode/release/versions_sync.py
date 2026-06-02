"""Sync .claude/versions.json latest_tags and current_implemented_tag from git tags."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_VTAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _version_tuple(tag: str) -> tuple[int, int, int]:
    m = _VTAG_RE.match(tag)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    message: str
    tags_found: list[str]
    new_current: str
    changed: bool


def _git_version_tags(project_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--sort=v:refname"],
        cwd=str(project_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [
        t.strip()
        for t in result.stdout.splitlines()
        if t.strip() and _VTAG_RE.match(t.strip())
    ]


def sync_versions_json(
    project_root: Path | None = None,
    dry_run: bool = False,
) -> SyncResult:
    """Update .claude/versions.json from git tags.

    Appends any git tags not yet in latest_tags (preserving the curated list)
    and updates current_implemented_tag to the newest tag.
    """
    root = project_root or Path.cwd()
    versions_path = root / ".claude" / "versions.json"

    if not versions_path.is_file():
        return SyncResult(
            ok=False,
            message=f"versions.json not found: {versions_path}",
            tags_found=[],
            new_current="",
            changed=False,
        )

    git_tags = _git_version_tags(root)
    if not git_tags:
        return SyncResult(
            ok=False,
            message="No vX.Y.Z git tags found.",
            tags_found=[],
            new_current="",
            changed=False,
        )

    payload = json.loads(versions_path.read_text(encoding="utf-8"))
    new_current = git_tags[-1]
    old_current = payload.get("current_implemented_tag", "")
    old_tags: list[str] = payload.get("latest_tags", [])
    old_tag_set = set(old_tags)

    # Merge git tags not yet listed, then sort by semver so latest_tags[-1] == new_current.
    new_tags_to_add = [t for t in git_tags if t not in old_tag_set]
    merged_tags = sorted(set(old_tags) | set(new_tags_to_add), key=_version_tuple)

    current_changed = old_current != new_current
    tags_changed = bool(new_tags_to_add) or (merged_tags != old_tags)
    changed = current_changed or tags_changed

    if not dry_run and changed:
        payload["latest_tags"] = merged_tags
        payload["current_implemented_tag"] = new_current
        versions_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    added_count = len(new_tags_to_add)
    if changed:
        msg = f"Synced: current={new_current}"
        if added_count:
            msg += f", added {added_count} tag(s)"
        msg += f". Total tags: {len(merged_tags)}."
    else:
        msg = f"Already up to date: current={new_current}, {len(old_tags)} tags."

    return SyncResult(
        ok=True,
        message=msg,
        tags_found=git_tags,
        new_current=new_current,
        changed=changed,
    )


def check_versions_json_stale(project_root: Path | None = None) -> SyncResult:
    """Return a result indicating whether versions.json is out of sync with git tags."""
    return sync_versions_json(project_root=project_root, dry_run=True)
