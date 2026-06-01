"""Tests for v2.6.15 release changelog generator."""

from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.changelog import generate_changelog, render_changelog


def _write_note(notes_dir: Path, name: str, heading: str, summary: str) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / name).write_text(
        f"# {heading}\n\n## Summary\n\n{summary}\n\n## Details\n\nMore.\n",
        encoding="utf-8",
    )


class TestGenerateChangelog:
    def test_includes_versions_in_range(self, tmp_path):
        notes = tmp_path / "docs" / "version-notes"
        _write_note(notes, "v2.6.14-release-command-ux-polish.md", "v2.6.14 — UX", "UX polish.")
        _write_note(notes, "v2.6.15-release-changelog-generator.md", "v2.6.15 — Changelog", "Changelog.")
        result = generate_changelog("2.6.14", "2.6.15", version_notes_dir=notes)
        assert result.ok
        assert [entry.version for entry in result.entries] == ["2.6.14", "2.6.15"]

    def test_excludes_versions_outside_range(self, tmp_path):
        notes = tmp_path / "docs" / "version-notes"
        _write_note(notes, "v2.6.13-old.md", "v2.6.13 — Old", "Old.")
        _write_note(notes, "v2.6.15-new.md", "v2.6.15 — New", "New.")
        result = generate_changelog("2.6.14", "2.6.15", version_notes_dir=notes)
        assert [entry.version for entry in result.entries] == ["2.6.15"]

    def test_invalid_version_reports_issue(self, tmp_path):
        result = generate_changelog("bad", "2.6.15", version_notes_dir=tmp_path)
        assert not result.ok
        assert "Invalid version" in result.issues[0]

    def test_from_after_to_reports_issue(self, tmp_path):
        result = generate_changelog("2.6.15", "2.6.14", version_notes_dir=tmp_path)
        assert not result.ok
        assert "must be <=" in result.issues[0]

    def test_missing_notes_dir_reports_issue(self, tmp_path):
        result = generate_changelog("2.6.14", "2.6.15", version_notes_dir=tmp_path / "missing")
        assert not result.ok
        assert "not found" in result.issues[0]


class TestRenderChangelog:
    def test_render_is_markdown(self, tmp_path):
        notes = tmp_path / "docs" / "version-notes"
        _write_note(notes, "v2.6.15-release-changelog-generator.md", "v2.6.15 — Changelog", "Builds changelog.")
        result = generate_changelog("2.6.15", "2.6.15", version_notes_dir=notes)
        text = render_changelog(result)
        assert "# Changelog v2.6.15..v2.6.15" in text
        assert "## v2.6.15" in text
        assert "Builds changelog." in text


class TestReleaseChangelogCLI:
    def test_cli_changelog_success(self, tmp_path, monkeypatch):
        notes = tmp_path / "docs" / "version-notes"
        _write_note(notes, "v2.6.15-release-changelog-generator.md", "v2.6.15 — Changelog", "Builds changelog.")
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["release", "changelog", "--from", "2.6.15", "--to", "2.6.15"])
        assert result.exit_code == 0
        assert "Changelog" in result.output
        assert "Builds changelog." in result.output

    def test_cli_changelog_failure_exits_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["release", "changelog", "--from", "bad", "--to", "2.6.15"])
        assert result.exit_code == 1
