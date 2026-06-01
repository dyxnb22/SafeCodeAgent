"""Tests for v2.7.9 release-surface-collapse-lite.

Verifies:
- sac release signoff output contains 'deprecated' notice.
- sac release checklist output contains 'planning helper' notice.
- Both commands remain callable (exit 0 for help, callable by CLI).
- docs/install-update.md main flow does not use signoff as a required step.
- docs/install-update.md main flow includes sync-versions-json.
"""

from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.checklist import render_release_checklist
from safecode.release.signoff import render_release_signoff, ReleaseSignoffResult

runner = CliRunner()


# ── Signoff deprecated notice ─────────────────────────────────────────────


class TestSignoffDeprecatedNotice:
    def test_render_signoff_contains_deprecated(self):
        """render_release_signoff output must mention 'deprecated'."""
        from safecode.release.check import ReleaseCheckResult
        from safecode.release.preflight import ReleasePreflightResult
        from safecode.release.smoke import SmokeTestResult, SmokeTestCase
        from safecode.release.metadata import ReleaseMetadata
        from safecode.release.docs_guard import DocsGuardResult
        from safecode.release.version_guard import TagConsistencyResult
        from safecode.release.versions_governance import VersionsGovernanceResult

        release_check = ReleaseCheckResult(
            package_version="2.7.9",
            runtime_version="2.7.9",
            version_consistent=True,
            version_message="OK",
            tree_clean=True,
            tree_detail="clean",
            tag_result=TagConsistencyResult(
                tag="v2.7.9",
                tag_available=True,
                consistent=True,
                package_version="2.7.9",
                message="OK",
            ),
            next_steps=[],
        )
        preflight = ReleasePreflightResult(
            release_check=release_check,
            smoke=SmokeTestResult(cases=[SmokeTestCase(name="x", passed=True, detail="ok")]),
            metadata=ReleaseMetadata(
                package_version="2.7.9",
                runtime_version="2.7.9",
                latest_git_tag="v2.7.9",
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
                current_git_tag="v2.7.9",
                implemented_tag="v2.7.9",
                skill_baseline_tags=["v2.7.9"],
                issues=[],
            ),
        )
        result = ReleaseSignoffResult(
            version="2.7.9",
            exact_tag="v2.7.9",
            release_check=release_check,
            preflight=preflight,
        )
        rendered = render_release_signoff(result)
        assert "deprecated" in rendered.lower(), f"Expected 'deprecated' in: {rendered}"

    def test_signoff_help_accessible(self):
        result = runner.invoke(app, ["release", "signoff", "--help"])
        assert result.exit_code == 0

    def test_signoff_help_mentions_internal_or_not_required(self):
        result = runner.invoke(app, ["release", "signoff", "--help"])
        assert "internal" in result.output.lower() or "not required" in result.output.lower()


# ── Checklist planning helper notice ─────────────────────────────────────


class TestChecklistPlanningHelperNotice:
    def test_render_checklist_contains_planning_helper(self):
        rendered = render_release_checklist("v2.7.9")
        assert "planning helper" in rendered.lower(), (
            f"Expected 'planning helper' in checklist output: {rendered[:200]}"
        )

    def test_render_checklist_not_a_release_gate(self):
        rendered = render_release_checklist("v2.7.9")
        assert "not a release gate" in rendered.lower() or "not a release gate" in rendered

    def test_checklist_help_accessible(self):
        result = runner.invoke(app, ["release", "checklist", "--help"])
        assert result.exit_code == 0

    def test_checklist_help_mentions_advanced(self):
        result = runner.invoke(app, ["release", "checklist", "--help"])
        assert "advanced" in result.output.lower()


# ── Docs main flow ────────────────────────────────────────────────────────


class TestDocsMainFlow:
    def _install_update_text(self) -> str:
        path = Path("docs/install-update.md")
        assert path.exists(), "docs/install-update.md not found"
        return path.read_text(encoding="utf-8")

    def test_main_flow_does_not_require_signoff(self):
        text = self._install_update_text()
        # signoff must not appear in the main flow code block
        # Find the main flow section
        main_flow_start = text.find("Recommended main path")
        assert main_flow_start >= 0
        # The main flow ends at the "Additional commands" section
        additional_start = text.find("Additional commands", main_flow_start)
        if additional_start == -1:
            additional_start = main_flow_start + 600
        main_flow_text = text[main_flow_start:additional_start]
        assert "signoff" not in main_flow_text, (
            "signoff should not appear in the main flow section"
        )

    def test_main_flow_includes_sync_versions_json(self):
        text = self._install_update_text()
        assert "sync-versions-json" in text, (
            "docs/install-update.md should mention sync-versions-json"
        )

    def test_main_flow_includes_preflight(self):
        text = self._install_update_text()
        assert "release preflight" in text
