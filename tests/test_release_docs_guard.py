"""Tests for v2.6.9 release docs finalization guard."""

from pathlib import Path

import pytest

from safecode.release.docs_guard import (
    RELEASE_COMMANDS,
    DocsGuardResult,
    check_docs_finalized,
)


class _Env:
    def __init__(self, tmp_path: Path, version: str = "2.6.9"):
        self.root = tmp_path
        self.version = version
        self.notes_dir = tmp_path / "docs" / "version-notes"
        self.notes_dir.mkdir(parents=True)
        self.skill_dir = tmp_path / ".claude" / "skills" / "current"
        self.skill_dir.mkdir(parents=True)
        self.readme = tmp_path / "README.md"
        self.install_doc = tmp_path / "docs" / "install-update.md"
        (tmp_path / "docs").mkdir(exist_ok=True)

    def write_note(self) -> None:
        (self.notes_dir / f"v{self.version}-feature.md").write_text("# note\n", encoding="utf-8")

    def write_skill(self, mention: bool = True) -> Path:
        p = self.skill_dir / "SKILL.md"
        text = f"# Baseline\nversion {self.version}\n" if mention else "# Baseline\n"
        p.write_text(text, encoding="utf-8")
        return p

    def write_readme(self, mention_cmds: bool = True) -> None:
        text = "# SafeCode\n\nRun sac release check to verify.\n" if mention_cmds else "# SafeCode\n"
        self.readme.write_text(text, encoding="utf-8")

    def write_install_doc(self, mention_cmds: bool = True) -> None:
        text = "# Install\n\nsac release smoke\n" if mention_cmds else "# Install\n"
        self.install_doc.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# check_docs_finalized
# ---------------------------------------------------------------------------


class TestCheckDocsFinalized:
    def test_all_pass(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        result = check_docs_finalized(
            "2.6.9",
            project_root=tmp_path,
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
            release_commands_documented=True,
        )
        assert result.ok is True
        assert result.has_version_note is True
        assert result.skill_mentions_version is True
        assert result.release_commands_documented is True

    def test_missing_version_note_fails(self, tmp_path):
        env = _Env(tmp_path)
        # No note written
        env.write_skill()
        result = check_docs_finalized(
            "2.6.9",
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
            release_commands_documented=True,
        )
        assert result.has_version_note is False
        assert result.ok is False
        assert any("version-note" in i.lower() or "v2.6.9" in i for i in result.issues)

    def test_stale_skill_fails(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill(mention=False)
        result = check_docs_finalized(
            "2.6.9",
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
            release_commands_documented=True,
        )
        assert result.skill_mentions_version is False
        assert result.ok is False
        assert any("SKILL.md" in i or "2.6.9" in i for i in result.issues)

    def test_missing_release_command_docs_fails(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        result = check_docs_finalized(
            "2.6.9",
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
            release_commands_documented=False,
        )
        assert result.release_commands_documented is False
        assert result.ok is False
        assert any("release" in i.lower() for i in result.issues)

    def test_readme_with_command_passes_docs_check(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        env.write_readme(mention_cmds=True)
        result = check_docs_finalized(
            "2.6.9",
            project_root=tmp_path,
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert result.release_commands_documented is True

    def test_install_doc_with_command_passes_docs_check(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        env.write_install_doc(mention_cmds=True)
        result = check_docs_finalized(
            "2.6.9",
            project_root=tmp_path,
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert result.release_commands_documented is True

    def test_no_docs_fails_commands_check(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        # No README or install-update written
        result = check_docs_finalized(
            "2.6.9",
            project_root=tmp_path,
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
        )
        assert result.release_commands_documented is False

    def test_issues_empty_when_all_ok(self, tmp_path):
        env = _Env(tmp_path)
        env.write_note()
        env.write_skill()
        result = check_docs_finalized(
            "2.6.9",
            notes_dir=env.notes_dir,
            skill_path=env.skill_dir / "SKILL.md",
            release_commands_documented=True,
        )
        assert result.issues == []

    def test_release_commands_constant_non_empty(self):
        assert len(RELEASE_COMMANDS) > 0
        assert any("sac release" in cmd for cmd in RELEASE_COMMANDS)

    def test_release_commands_include_bump_and_preflight(self):
        assert "sac release bump" in RELEASE_COMMANDS
        assert "sac release preflight" in RELEASE_COMMANDS
