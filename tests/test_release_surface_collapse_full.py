"""Tests for v2.8.5 release-surface-collapse-full.

Verifies:
- sac release --help shows only preflight, bump, changelog (not hidden commands).
- checklist, check, smoke, meta, signoff are callable but hidden from --help.
- sac release signoff emits a RuntimeWarning pointing to preflight.
- docs/install-update.md presents one main release flow with hidden helpers noted.
"""

import warnings
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


# ── Visible commands in sac release --help ───────────────────────────────────


class TestReleaseHelpSurface:
    def _release_help(self) -> str:
        result = runner.invoke(app, ["release", "--help"])
        assert result.exit_code == 0, f"release --help failed: {result.output}"
        return result.output

    def test_preflight_visible(self):
        assert "preflight" in self._release_help()

    def test_bump_visible(self):
        assert "bump" in self._release_help()

    def test_changelog_visible(self):
        assert "changelog" in self._release_help()

    def test_checklist_hidden(self):
        output = self._release_help()
        lines = output.splitlines()
        # "checklist" must NOT appear as a listed command in the help surface
        command_lines = [ln for ln in lines if ln.strip().startswith("checklist")]
        assert not command_lines, f"checklist should be hidden, found: {command_lines}"

    def test_check_hidden(self):
        output = self._release_help()
        lines = output.splitlines()
        command_lines = [ln for ln in lines if ln.strip().startswith("check ") or ln.strip() == "check"]
        assert not command_lines, f"check should be hidden, found: {command_lines}"

    def test_smoke_hidden(self):
        output = self._release_help()
        lines = output.splitlines()
        command_lines = [ln for ln in lines if ln.strip().startswith("smoke")]
        assert not command_lines, f"smoke should be hidden, found: {command_lines}"

    def test_meta_hidden(self):
        output = self._release_help()
        lines = output.splitlines()
        command_lines = [ln for ln in lines if ln.strip().startswith("meta")]
        assert not command_lines, f"meta should be hidden, found: {command_lines}"

    def test_signoff_hidden(self):
        output = self._release_help()
        lines = output.splitlines()
        command_lines = [ln for ln in lines if ln.strip().startswith("signoff")]
        assert not command_lines, f"signoff should be hidden, found: {command_lines}"


# ── Hidden commands remain callable ──────────────────────────────────────────


class TestHiddenCommandsCallable:
    def test_checklist_help_callable(self):
        result = runner.invoke(app, ["release", "checklist", "--help"])
        assert result.exit_code == 0

    def test_check_help_callable(self):
        result = runner.invoke(app, ["release", "check", "--help"])
        assert result.exit_code == 0

    def test_smoke_help_callable(self):
        result = runner.invoke(app, ["release", "smoke", "--help"])
        assert result.exit_code == 0

    def test_meta_help_callable(self):
        result = runner.invoke(app, ["release", "meta", "--help"])
        assert result.exit_code == 0

    def test_signoff_help_callable(self):
        result = runner.invoke(app, ["release", "signoff", "--help"])
        assert result.exit_code == 0

    def test_checklist_help_mentions_advanced(self):
        result = runner.invoke(app, ["release", "checklist", "--help"])
        assert "advanced" in result.output.lower()

    def test_signoff_help_mentions_internal(self):
        result = runner.invoke(app, ["release", "signoff", "--help"])
        assert "internal" in result.output.lower()


# ── Signoff RuntimeWarning ────────────────────────────────────────────────────


class TestSignoffRuntimeWarning:
    def test_signoff_emits_runtime_warning(self):
        """Invoking sac release signoff must emit a RuntimeWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            runner.invoke(app, ["release", "signoff"])
        runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime_warnings, "Expected at least one RuntimeWarning from sac release signoff"

    def test_signoff_warning_mentions_preflight(self):
        """The RuntimeWarning message must reference sac release preflight."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            runner.invoke(app, ["release", "signoff"])
        msgs = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
        assert any("preflight" in m.lower() for m in msgs), (
            f"Expected 'preflight' in RuntimeWarning messages, got: {msgs}"
        )

    def test_signoff_render_still_contains_deprecated(self):
        """The rendered signoff output still contains 'deprecated' notice."""
        from safecode.release.signoff import render_release_signoff, ReleaseSignoffResult
        from safecode.release.check import ReleaseCheckResult
        from safecode.release.preflight import ReleasePreflightResult
        from safecode.release.smoke import SmokeTestResult, SmokeTestCase
        from safecode.release.metadata import ReleaseMetadata
        from safecode.release.docs_guard import DocsGuardResult
        from safecode.release.version_guard import TagConsistencyResult
        from safecode.release.versions_governance import VersionsGovernanceResult

        release_check = ReleaseCheckResult(
            package_version="2.8.5",
            runtime_version="2.8.5",
            version_consistent=True,
            version_message="OK",
            tree_clean=True,
            tree_detail="clean",
            tag_result=TagConsistencyResult(
                tag="v2.8.5",
                tag_available=True,
                consistent=True,
                package_version="2.8.5",
                message="OK",
            ),
            next_steps=[],
        )
        preflight = ReleasePreflightResult(
            release_check=release_check,
            smoke=SmokeTestResult(cases=[SmokeTestCase(name="x", passed=True, detail="ok")]),
            metadata=ReleaseMetadata(
                package_version="2.8.5",
                runtime_version="2.8.5",
                latest_git_tag="v2.8.5",
                version_note_files=[],
                has_version_note=True,
                skill_mentions_version=True,
                issues=[],
            ),
            docs=DocsGuardResult(
                has_version_note=True,
                skill_mentions_version=True,
                release_commands_documented=True,
                issues=[],
            ),
            versions_governance=VersionsGovernanceResult(
                versions_json_ok=True,
                skill_ok=True,
                current_git_tag="v2.8.5",
                implemented_tag="v2.8.5",
                skill_baseline_tags=["v2.8.5"],
                issues=[],
            ),
        )
        result = ReleaseSignoffResult(
            version="2.8.5",
            exact_tag="v2.8.5",
            release_check=release_check,
            preflight=preflight,
        )
        rendered = render_release_signoff(result)
        assert "deprecated" in rendered.lower()


# ── Checklist planning-helper behavior ───────────────────────────────────────


class TestChecklistPlanningHelper:
    def test_checklist_render_contains_planning_helper(self):
        from safecode.release.checklist import render_release_checklist
        rendered = render_release_checklist("v2.8.5")
        assert "planning helper" in rendered.lower()

    def test_checklist_render_not_a_release_gate(self):
        from safecode.release.checklist import render_release_checklist
        rendered = render_release_checklist("v2.8.5")
        assert "not a release gate" in rendered.lower()


# ── Docs: one main release flow ───────────────────────────────────────────────


class TestDocsMainReleaseFlow:
    def _docs_text(self) -> str:
        path = Path("docs/install-update.md")
        assert path.exists(), "docs/install-update.md not found"
        return path.read_text(encoding="utf-8")

    def test_main_flow_shows_preflight(self):
        assert "release preflight" in self._docs_text()

    def test_main_flow_shows_bump(self):
        assert "release bump" in self._docs_text()

    def test_main_flow_shows_changelog(self):
        assert "release changelog" in self._docs_text()

    def test_hidden_helpers_noted_as_hidden(self):
        text = self._docs_text()
        assert "hidden" in text.lower(), "docs should note that helpers are hidden from --help"

    def test_signoff_noted_as_deprecated(self):
        text = self._docs_text()
        assert "deprecated" in text.lower()
