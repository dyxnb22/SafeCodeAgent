"""Tests for v2.7.4 release-surface-honesty-lite.

Verifies that:
- Internal/advanced release commands are labelled in their help text.
- Core recommended commands (bump, preflight, changelog) are not labelled as internal/deprecated.
- All commands remain callable (not removed).
"""

from typer.testing import CliRunner

from safecode.cli import app


class TestReleaseHelpLabels:
    def _help(self, *args: str) -> str:
        result = CliRunner().invoke(app, list(args) + ["--help"])
        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        return result.output

    def test_signoff_labelled_internal(self):
        output = self._help("release", "signoff")
        assert "[internal]" in output.lower() or "not required" in output.lower()

    def test_checklist_labelled_advanced(self):
        output = self._help("release", "checklist")
        assert "[advanced]" in output.lower()

    def test_check_labelled_advanced(self):
        output = self._help("release", "check")
        assert "[advanced]" in output.lower()

    def test_smoke_labelled_advanced(self):
        output = self._help("release", "smoke")
        assert "[advanced]" in output.lower()

    def test_meta_labelled_advanced(self):
        output = self._help("release", "meta")
        assert "[advanced]" in output.lower()

    def test_bump_is_not_labelled_internal_or_deprecated(self):
        output = self._help("release", "bump")
        assert "[internal]" not in output.lower()
        assert "[deprecated]" not in output.lower()

    def test_preflight_is_not_labelled_internal_or_deprecated(self):
        output = self._help("release", "preflight")
        assert "[internal]" not in output.lower()
        assert "[deprecated]" not in output.lower()

    def test_changelog_is_not_labelled_internal_or_deprecated(self):
        output = self._help("release", "changelog")
        assert "[internal]" not in output.lower()
        assert "[deprecated]" not in output.lower()


class TestReleaseCommandsRemainCallable:
    def test_bump_help_runs(self):
        result = CliRunner().invoke(app, ["release", "bump", "--help"])
        assert result.exit_code == 0

    def test_signoff_help_runs(self):
        result = CliRunner().invoke(app, ["release", "signoff", "--help"])
        assert result.exit_code == 0

    def test_checklist_help_runs(self):
        result = CliRunner().invoke(app, ["release", "checklist", "--help"])
        assert result.exit_code == 0

    def test_check_help_runs(self):
        result = CliRunner().invoke(app, ["release", "check", "--help"])
        assert result.exit_code == 0

    def test_smoke_help_runs(self):
        result = CliRunner().invoke(app, ["release", "smoke", "--help"])
        assert result.exit_code == 0

    def test_meta_help_runs(self):
        result = CliRunner().invoke(app, ["release", "meta", "--help"])
        assert result.exit_code == 0

    def test_preflight_help_runs(self):
        result = CliRunner().invoke(app, ["release", "preflight", "--help"])
        assert result.exit_code == 0

    def test_changelog_help_runs(self):
        result = CliRunner().invoke(app, ["release", "changelog", "--help"])
        assert result.exit_code == 0


class TestInstallUpdateDocsMentionsPreferredFlow:
    def test_docs_recommend_preflight_not_signoff_in_main_flow(self):
        from pathlib import Path
        docs = (Path(".") / "docs" / "install-update.md").read_text(encoding="utf-8")
        assert "sac release preflight" in docs
        # signoff must only appear in the advanced/internal section, not as a main-flow step
        flow_section = docs.split("## Release Flow")[1]
        # Extract just the first code block (the recommended path)
        main_block_start = flow_section.find("```bash")
        main_block_end = flow_section.find("```\n\n", main_block_start + 5)
        main_code = flow_section[main_block_start:main_block_end]
        assert "signoff" not in main_code

    def test_docs_main_flow_is_bump_pytest_tag_preflight(self):
        from pathlib import Path
        docs = (Path(".") / "docs" / "install-update.md").read_text(encoding="utf-8")
        flow_section = docs.split("## Release Flow")[1]
        # bump appears before preflight in the main flow
        bump_pos = flow_section.find("release bump")
        preflight_pos = flow_section.find("release preflight")
        assert bump_pos != -1 and preflight_pos != -1
        assert bump_pos < preflight_pos
