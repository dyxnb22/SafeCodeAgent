"""Versions governance preflight check (v2.7.8).

Verifies that:
1. .claude/versions.json current_implemented_tag matches the latest git tag.
2. .agents/skills/current/SKILL.md has exactly one unambiguous baseline tag.

When stale, the suggested next step is ``sac release sync-versions-json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from safecode.release.versions_sync import _git_version_tags  # shared helper

_BASELINE_TAG_RE = re.compile(r"Implemented\. Git baseline: tag\s+`(v\d+\.\d+\.\d+)`")


@dataclass(frozen=True)
class VersionsGovernanceResult:
    """Result of the versions governance preflight check."""

    versions_json_ok: bool
    skill_ok: bool
    current_git_tag: str
    implemented_tag: str
    skill_baseline_tags: list[str]
    issues: list[str]

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def check_versions_governance(
    project_root: Path | None = None,
    *,
    git_tags: list[str] | None = None,
) -> VersionsGovernanceResult:
    """Check versions.json sync and SKILL.md baseline tag consistency.

    ``git_tags`` can be injected for testing without a real git repo.
    """
    root = project_root or Path.cwd()
    issues: list[str] = []

    # ── 1. versions.json check ────────────────────────────────────────────
    versions_path = root / ".claude" / "versions.json"
    tags = git_tags if git_tags is not None else _git_version_tags(root)
    latest_tag = tags[-1] if tags else ""
    implemented_tag = ""
    versions_json_ok = False

    if not versions_path.is_file():
        issues.append(f"Missing versions.json: {versions_path}")
    else:
        try:
            payload = json.loads(versions_path.read_text(encoding="utf-8"))
            implemented_tag = payload.get("current_implemented_tag", "")
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(f"Cannot read versions.json: {exc}")
            implemented_tag = ""

        if not latest_tag:
            issues.append("No vX.Y.Z git tags found; cannot verify versions.json.")
        elif implemented_tag != latest_tag:
            issues.append(
                f"versions.json current_implemented_tag={implemented_tag!r} "
                f"is stale (latest git tag: {latest_tag!r}). "
                f"Run: sac release sync-versions-json"
            )
        else:
            versions_json_ok = True

    # ── 2. SKILL.md baseline tag check ───────────────────────────────────
    skill_path = root / ".agents" / "skills" / "current" / "SKILL.md"
    skill_baseline_tags: list[str] = []
    skill_ok = False

    if not skill_path.is_file():
        issues.append(f"Missing SKILL.md: {skill_path}")
    else:
        try:
            text = skill_path.read_text(encoding="utf-8")
            skill_baseline_tags = _BASELINE_TAG_RE.findall(text)
        except OSError as exc:
            issues.append(f"Cannot read SKILL.md: {exc}")

        if len(skill_baseline_tags) == 0:
            issues.append("SKILL.md has no 'Git baseline: tag `vX.Y.Z`' entry.")
        elif len(set(skill_baseline_tags)) > 1:
            issues.append(
                f"SKILL.md has multiple conflicting baseline tags: "
                f"{', '.join(repr(t) for t in sorted(set(skill_baseline_tags)))}. "
                f"Keep only one current baseline."
            )
        else:
            skill_ok = True

    return VersionsGovernanceResult(
        versions_json_ok=versions_json_ok,
        skill_ok=skill_ok,
        current_git_tag=latest_tag,
        implemented_tag=implemented_tag,
        skill_baseline_tags=skill_baseline_tags,
        issues=issues,
    )
