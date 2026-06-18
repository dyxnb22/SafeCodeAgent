"""Tests for v2.7.8 versions-governance-preflight.

Verifies:
- Stale versions.json (current_implemented_tag != latest git tag) fails.
- Current real repo passes versions governance check.
- SKILL.md with multiple conflicting baseline tags fails.
- Preflight integrates the governance check.
- next step message mentions sac release sync-versions-json on stale versions.json.
"""

import json
from pathlib import Path

import pytest

from safecode.release.versions_governance import (
    VersionsGovernanceResult,
    check_versions_governance,
)


# ── Fixture helpers ───────────────────────────────────────────────────────

def _write_versions_json(path: Path, current_tag: str, latest_tags: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "current_implemented_tag": current_tag,
                "latest_tags": latest_tags,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_skill_md(path: Path, *baseline_tags: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Current Baseline\n\n## Status\n"]
    for tag in baseline_tags:
        lines.append(f"Implemented. Git baseline: tag `{tag}`.\n\n")
    # Also include a non-matching list-item reference to ensure it's not counted.
    lines.append("## Source Of Truth\n- Git baseline: tag `v0.0.0`\n")
    path.write_text("".join(lines), encoding="utf-8")


# ── versions.json staleness ───────────────────────────────────────────────


class TestVersionsJsonStaleness:
    def test_stale_versions_json_fails(self, tmp_path: Path) -> None:
        _write_versions_json(
            tmp_path / ".claude" / "versions.json",
            current_tag="v2.7.0",
            latest_tags=["v2.7.0"],
        )
        _write_skill_md(tmp_path / ".agents" / "skills" / "current" / "SKILL.md", "v2.7.0")

        result = check_versions_governance(
            tmp_path,
            git_tags=["v2.7.0", "v2.7.1"],  # latest is v2.7.1, but json says v2.7.0
        )

        assert not result.ok
        assert not result.versions_json_ok
        assert any("sync-versions-json" in issue for issue in result.issues), (
            f"Expected next-step hint in issues: {result.issues}"
        )

    def test_up_to_date_versions_json_passes(self, tmp_path: Path) -> None:
        _write_versions_json(
            tmp_path / ".claude" / "versions.json",
            current_tag="v2.7.1",
            latest_tags=["v2.7.0", "v2.7.1"],
        )
        _write_skill_md(tmp_path / ".agents" / "skills" / "current" / "SKILL.md", "v2.7.1")

        result = check_versions_governance(
            tmp_path,
            git_tags=["v2.7.0", "v2.7.1"],
        )

        assert result.ok
        assert result.versions_json_ok

    def test_missing_versions_json_fails(self, tmp_path: Path) -> None:
        _write_skill_md(tmp_path / ".agents" / "skills" / "current" / "SKILL.md", "v2.7.0")

        result = check_versions_governance(tmp_path, git_tags=["v2.7.0"])

        assert not result.ok
        assert any("versions.json" in issue for issue in result.issues)


# ── SKILL.md baseline tag checks ─────────────────────────────────────────


class TestSkillBaselineTags:
    def test_single_baseline_tag_passes(self, tmp_path: Path) -> None:
        _write_versions_json(
            tmp_path / ".claude" / "versions.json",
            current_tag="v2.7.0",
            latest_tags=["v2.7.0"],
        )
        _write_skill_md(tmp_path / ".agents" / "skills" / "current" / "SKILL.md", "v2.7.0")

        result = check_versions_governance(tmp_path, git_tags=["v2.7.0"])

        assert result.skill_ok
        assert result.skill_baseline_tags == ["v2.7.0"]

    def test_double_conflicting_baseline_tags_fails(self, tmp_path: Path) -> None:
        _write_versions_json(
            tmp_path / ".claude" / "versions.json",
            current_tag="v2.7.0",
            latest_tags=["v2.7.0"],
        )
        # Two different baseline tags → contradiction
        _write_skill_md(
            tmp_path / ".agents" / "skills" / "current" / "SKILL.md",
            "v2.7.0",
            "v2.7.1",
        )

        result = check_versions_governance(tmp_path, git_tags=["v2.7.0"])

        assert not result.ok
        assert not result.skill_ok
        assert any("conflicting" in issue for issue in result.issues)

    def test_missing_skill_md_fails(self, tmp_path: Path) -> None:
        _write_versions_json(
            tmp_path / ".claude" / "versions.json",
            current_tag="v2.7.0",
            latest_tags=["v2.7.0"],
        )

        result = check_versions_governance(tmp_path, git_tags=["v2.7.0"])

        assert not result.ok
        assert not result.skill_ok

    def test_skill_with_no_baseline_tag_fails(self, tmp_path: Path) -> None:
        _write_versions_json(
            tmp_path / ".claude" / "versions.json",
            current_tag="v2.7.0",
            latest_tags=["v2.7.0"],
        )
        (tmp_path / ".agents" / "skills" / "current").mkdir(parents=True)
        (tmp_path / ".agents" / "skills" / "current" / "SKILL.md").write_text(
            "# Baseline\n\nNo tag here.\n", encoding="utf-8"
        )

        result = check_versions_governance(tmp_path, git_tags=["v2.7.0"])

        assert not result.skill_ok


# ── Real repo check ───────────────────────────────────────────────────────


class TestCurrentRepoPassesGovernance:
    def test_current_repo_governance_passes(self) -> None:
        """The actual repo must pass versions governance (real git tags)."""
        result = check_versions_governance(Path("."))
        assert result.ok, f"Governance issues: {result.issues}"


# ── Preflight integration ─────────────────────────────────────────────────


class TestPreflightIntegration:
    def test_preflight_includes_governance_check(self, tmp_path: Path) -> None:
        """run_release_preflight accepts and uses a versions_governance_runner."""
        from safecode.release.preflight import run_release_preflight
        from safecode.release.versions_governance import VersionsGovernanceResult

        stub_governance = VersionsGovernanceResult(
            versions_json_ok=True,
            skill_ok=True,
            current_git_tag="v2.7.7",
            implemented_tag="v2.7.7",
            skill_baseline_tags=["v2.7.7"],
            issues=[],
        )

        result = run_release_preflight(
            project_root=Path("."),
            versions_governance_runner=lambda _root: stub_governance,
        )

        assert result.versions_governance is not None
        assert result.versions_governance.ok

    def test_preflight_fails_when_governance_stale(self, tmp_path: Path) -> None:
        from safecode.release.preflight import run_release_preflight
        from safecode.release.versions_governance import VersionsGovernanceResult

        stale_governance = VersionsGovernanceResult(
            versions_json_ok=False,
            skill_ok=True,
            current_git_tag="v2.7.7",
            implemented_tag="v2.7.0",
            skill_baseline_tags=["v2.7.7"],
            issues=["versions.json stale; run: sac release sync-versions-json"],
        )

        result = run_release_preflight(
            project_root=Path("."),
            versions_governance_runner=lambda _root: stale_governance,
        )

        assert not result.ok

    def test_preflight_render_includes_governance(self, tmp_path: Path) -> None:
        from safecode.release.preflight import run_release_preflight, render_release_preflight

        result = run_release_preflight(project_root=Path("."))
        rendered = render_release_preflight(result)
        assert "versions governance" in rendered
