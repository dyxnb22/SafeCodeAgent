"""Tests for v2.6.8 release metadata index."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.metadata import (
    ReleaseMetadata,
    collect_release_metadata,
    render_release_metadata,
)


class _Env:
    """Helper to build a minimal temp-dir environment for metadata tests."""

    def __init__(self, tmp_path: Path, version: str = "2.6.8"):
        self.root = tmp_path
        self.version = version
        self.notes_dir = tmp_path / "docs" / "version-notes"
        self.notes_dir.mkdir(parents=True)
        self.skill_dir = tmp_path / ".claude" / "skills" / "current"
        self.skill_dir.mkdir(parents=True)

    def write_note(self, name: str | None = None) -> Path:
        fname = name or f"v{self.version}-feature.md"
        p = self.notes_dir / fname
        p.write_text(f"# {fname}\n", encoding="utf-8")
        return p

    def write_skill(self, mention_version: bool = True) -> Path:
        p = self.skill_dir / "SKILL.md"
        content = f"# Baseline\nCurrent version: {self.version}\n" if mention_version else "# Baseline\n"
        p.write_text(content, encoding="utf-8")
        return p


# ---------------------------------------------------------------------------
# collect_release_metadata
# ---------------------------------------------------------------------------


class TestCollectReleaseMetadata:
    def test_returns_correct_package_version(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag="v2.6.8",
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.package_version == "2.6.8"
        assert meta.runtime_version == "2.6.8"

    def test_latest_git_tag_injected(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag="v2.6.7",
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.latest_git_tag == "v2.6.7"

    def test_no_tag_is_none(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.latest_git_tag is None

    def test_has_version_note_when_note_exists(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.has_version_note is True

    def test_missing_version_note_reported(self, tmp_path):
        env = _Env(tmp_path)
        env.write_skill()
        # No note written
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.has_version_note is False
        assert any("version-note" in issue.lower() or "v2.6.8" in issue for issue in meta.issues)

    def test_skill_mentions_version(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill(mention_version=True)
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.skill_mentions_version is True

    def test_stale_skill_reported(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill(mention_version=False)
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.skill_mentions_version is False
        assert any("SKILL.md" in issue or "2.6.8" in issue for issue in meta.issues)

    def test_ok_when_note_and_skill_present(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert meta.ok is True

    def test_version_note_files_listed(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note("v2.6.7-previous.md")
        env.write_note("v2.6.8-feature.md")
        env.write_skill()
        meta = collect_release_metadata(
            tmp_path,
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert "v2.6.7-previous.md" in meta.version_note_files
        assert "v2.6.8-feature.md" in meta.version_note_files


# ---------------------------------------------------------------------------
# render_release_metadata
# ---------------------------------------------------------------------------


class TestRenderReleaseMetadata:
    def _make_meta(
        self,
        *,
        package_version: str = "2.6.8",
        runtime_version: str = "2.6.8",
        latest_git_tag: str | None = "v2.6.8",
        has_version_note: bool = True,
        skill_mentions_version: bool = True,
        issues: list[str] | None = None,
    ) -> ReleaseMetadata:
        return ReleaseMetadata(
            package_version=package_version,
            runtime_version=runtime_version,
            latest_git_tag=latest_git_tag,
            version_note_files=[f"v{package_version}-feature.md"],
            has_version_note=has_version_note,
            skill_mentions_version=skill_mentions_version,
            issues=issues or [],
        )

    def test_render_includes_package_version(self):
        meta = self._make_meta()
        text = render_release_metadata(meta)
        assert "2.6.8" in text

    def test_render_shows_tag(self):
        meta = self._make_meta(latest_git_tag="v2.6.8")
        text = render_release_metadata(meta)
        assert "v2.6.8" in text

    def test_render_shows_none_for_no_tag(self):
        meta = self._make_meta(latest_git_tag=None)
        text = render_release_metadata(meta)
        assert "(none)" in text

    def test_render_shows_issue_when_note_missing(self):
        meta = self._make_meta(has_version_note=False, issues=["No version-note file found for v2.6.8."])
        text = render_release_metadata(meta)
        assert "Issues" in text or "version-note" in text.lower()

    def test_render_shows_ok_when_clean(self):
        meta = self._make_meta()
        text = render_release_metadata(meta)
        assert "good" in text.lower() or "ok" in text.lower()

    def test_render_includes_note_count(self):
        meta = ReleaseMetadata(
            package_version="2.6.8",
            runtime_version="2.6.8",
            latest_git_tag=None,
            version_note_files=["v2.6.7-a.md", "v2.6.8-b.md"],
            has_version_note=True,
            skill_mentions_version=True,
            issues=[],
        )
        text = render_release_metadata(meta)
        assert "2" in text  # count of notes


# ---------------------------------------------------------------------------
# CLI: sac release meta
# ---------------------------------------------------------------------------


class TestReleaseMetaCLI:
    def test_cli_meta_exits_zero_when_ok(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from safecode import cli_ops

        def _fake():
            return ReleaseMetadata(
                package_version="2.6.8",
                runtime_version="2.6.8",
                latest_git_tag="v2.6.8",
                version_note_files=["v2.6.8-feature.md"],
                has_version_note=True,
                skill_mentions_version=True,
                issues=[],
            )

        monkeypatch.setattr(cli_ops, "collect_release_metadata", lambda *a, **kw: _fake())
        result = CliRunner().invoke(app, ["release", "meta"])
        assert result.exit_code == 0
        assert "2.6.8" in result.output

    def test_cli_meta_exits_nonzero_when_issues(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from safecode import cli_ops

        def _fake():
            return ReleaseMetadata(
                package_version="2.6.8",
                runtime_version="2.6.8",
                latest_git_tag=None,
                version_note_files=[],
                has_version_note=False,
                skill_mentions_version=False,
                issues=["No version-note for v2.6.8.", "SKILL.md stale."],
            )

        monkeypatch.setattr(cli_ops, "collect_release_metadata", lambda *a, **kw: _fake())
        result = CliRunner().invoke(app, ["release", "meta"])
        assert result.exit_code != 0
