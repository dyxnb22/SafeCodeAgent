"""Tests for root-level project hygiene files (v5.6.0)."""

import os
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


class TestHygieneFilesExist:
    def test_license_exists(self):
        assert (_ROOT / "LICENSE").exists(), "LICENSE file missing"

    def test_security_md_exists(self):
        assert (_ROOT / "SECURITY.md").exists(), "SECURITY.md missing"

    def test_contributing_md_exists(self):
        assert (_ROOT / "CONTRIBUTING.md").exists(), "CONTRIBUTING.md missing"

    def test_changelog_md_exists(self):
        assert (_ROOT / "CHANGELOG.md").exists(), "CHANGELOG.md missing"


class TestLicenseContent:
    def test_license_is_non_empty(self):
        text = (_ROOT / "LICENSE").read_text()
        assert len(text) > 50

    def test_license_contains_mit_or_copyright(self):
        text = (_ROOT / "LICENSE").read_text().lower()
        assert "mit" in text or "copyright" in text


class TestSecurityMd:
    def test_contains_security_model_section(self):
        text = (_ROOT / "SECURITY.md").read_text()
        assert "Security Model" in text or "security model" in text.lower()

    def test_mentions_threat_model(self):
        text = (_ROOT / "SECURITY.md").read_text()
        assert "threat-model" in text or "threat model" in text.lower()

    def test_mentions_approval(self):
        text = (_ROOT / "SECURITY.md").read_text().lower()
        assert "approval" in text


class TestContributingMd:
    def _text(self):
        return (_ROOT / "CONTRIBUTING.md").read_text()

    def test_has_dev_setup_section(self):
        assert "setup" in self._text().lower()

    def test_has_test_section(self):
        assert "test" in self._text().lower()

    def test_mentions_native_tool(self):
        text = self._text().lower()
        assert "native tool" in text or "nativetool" in text

    def test_mentions_mock(self):
        assert "mock" in self._text().lower()


class TestChangelogMd:
    def _text(self):
        return (_ROOT / "CHANGELOG.md").read_text()

    def test_has_unreleased_section(self):
        assert "Unreleased" in self._text()

    def test_has_v5_entry(self):
        text = self._text()
        assert "v5." in text

    def test_changelog_is_non_empty(self):
        assert len(self._text()) > 100


class TestReadmeEnterpriseBranchContext:
    def _readme(self):
        return (_ROOT / "README.md").read_text()

    def test_homebrew_not_presented_as_primary_channel(self):
        text = self._readme()
        # Homebrew should not appear as a recommended install path in the first screen.
        # Absence is preferred; a brew install code block is not.
        lines = text.splitlines()
        brew_block_active = False
        for line in lines:
            if "brew tap" in line or "brew install" in line:
                # If it's in a code block, check surrounding context
                context_start = max(0, lines.index(line) - 5)
                context = "\n".join(lines[context_start : lines.index(line) + 3]).lower()
                assert "recommended" not in context, (
                    "Homebrew presented as recommended install path in README"
                )

    def test_readme_does_not_advertise_homebrew_soon(self):
        text = self._readme().lower()
        assert "homebrew tap: coming soon" not in text

    def test_readme_identifies_enterprise_branch(self):
        text = self._readme()
        assert "SafeCodeAgent Enterprise" in text
        assert "enterprise security engineering agent platform" in text

    def test_readme_links_enterprise_docs(self):
        text = self._readme()
        assert "product-planning/README.md" in text
        assert "enterprise-docs/architecture.md" in text

    def test_readme_shows_safety_invariants(self):
        text = self._readme()
        lower = text.lower()
        assert "model output is never execution authority" in lower
        assert "policy-gated" in lower
        assert "recoverable" in lower


# ---------------------------------------------------------------------------
# v5.7.2: docs and contract polish
# ---------------------------------------------------------------------------


class TestChangelogContent:
    def _text(self):
        return (_ROOT / "CHANGELOG.md").read_text()

    def test_changelog_has_unreleased_section(self):
        assert "Unreleased" in self._text()

    def test_changelog_has_v5x_section(self):
        assert "v5." in self._text()

    def test_changelog_has_v57_entry(self):
        assert "v5.7" in self._text() or "v5.7.1" in self._text() or "v5.7.2" in self._text()

    def test_changelog_is_non_empty(self):
        assert len(self._text()) > 100

    def test_changelog_format_has_markers(self):
        text = self._text()
        assert "## [" in text  # version heading format


class TestContributingContent:
    def _text(self):
        return (_ROOT / "CONTRIBUTING.md").read_text()

    def test_contributing_mentions_native_tool_howto(self):
        text = self._text()
        assert "native tool" in text.lower()
        assert "NativeToolSpec" in text

    def test_contributing_mentions_llm_provider_howto(self):
        text = self._text()
        assert "LLM provider" in text or "provider" in text.lower()

    def test_contributing_mentions_test_conventions(self):
        text = self._text()
        assert "test" in text.lower()
        assert "pytest" in text.lower()

    def test_contributing_mentions_mock_by_default(self):
        text = self._text()
        assert "mock" in text.lower()

    def test_contributing_has_dev_setup(self):
        assert "setup" in self._text().lower()

    def test_contributing_has_commit_message_style(self):
        assert "commit message" in self._text().lower() or "type(scope)" in self._text()


class TestGenerateChangelogScript:
    def test_script_not_required(self):
        """The generate-changelog.sh script is optional."""
        script = _ROOT / "scripts" / "generate-changelog.sh"
        if script.exists():
            assert os.access(str(script), os.X_OK), "generate-changelog.sh must be executable"
