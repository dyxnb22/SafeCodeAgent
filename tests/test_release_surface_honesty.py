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
        from safecode.cli_ops import release_checklist
        assert "[advanced]" in output.lower() or "[advanced]" in (release_checklist.__doc__ or "").lower()

    def test_check_labelled_advanced(self):
        output = self._help("release", "check")
        from safecode.cli_ops import release_check
        assert "[advanced]" in output.lower() or "[advanced]" in (release_check.__doc__ or "").lower()

    def test_smoke_labelled_advanced(self):
        output = self._help("release", "smoke")
        from safecode.cli_ops import release_smoke
        assert "[advanced]" in output.lower() or "[advanced]" in (release_smoke.__doc__ or "").lower()

    def test_meta_labelled_advanced(self):
        output = self._help("release", "meta")
        from safecode.cli_ops import release_meta
        assert "[advanced]" in output.lower() or "[advanced]" in (release_meta.__doc__ or "").lower()

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
