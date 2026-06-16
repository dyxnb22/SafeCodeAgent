"""Docs claims guard for v4.9 AI shell documentation."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_DOCS = _REPO_ROOT / "docs"
_README = _REPO_ROOT / "README.md"


# ---------------------------------------------------------------------------
# Tutorial existence
# ---------------------------------------------------------------------------


class TestTutorialExists:
    def test_ai_shell_tutorial_exists(self):
        """docs/tutorials/ai-shell-first-hour.md must exist."""
        tutorial = _DOCS / "tutorials" / "ai-shell-first-hour.md"
        assert tutorial.exists(), "AI shell tutorial must exist"

    def test_ai_shell_tutorial_has_sac_shell(self):
        """AI shell tutorial must document 'sac shell' command."""
        content = (_DOCS / "tutorials" / "ai-shell-first-hour.md").read_text()
        assert "sac shell" in content

    def test_ai_shell_tutorial_experimental_label(self):
        """AI shell tutorial must carry the EXPERIMENTAL label."""
        content = (_DOCS / "tutorials" / "ai-shell-first-hour.md").read_text()
        assert "EXPERIMENTAL" in content

    def test_ai_shell_tutorial_no_auto_apply(self):
        """AI shell tutorial must state no auto-apply."""
        content = (_DOCS / "tutorials" / "ai-shell-first-hour.md").read_text().lower()
        assert "no auto-apply" in content or "never auto-applies" in content or "not applied" in content

    def test_ai_shell_tutorial_no_rag(self):
        """AI shell tutorial must state no RAG."""
        content = (_DOCS / "tutorials" / "ai-shell-first-hour.md").read_text().lower()
        assert "no rag" in content or "no embeddings" in content

    def test_ai_shell_tutorial_no_v5_promise(self):
        """AI shell tutorial must not promise v5."""
        content = (_DOCS / "tutorials" / "ai-shell-first-hour.md").read_text().lower()
        assert "v5" not in content or "schedule" not in content


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


class TestReadmeCoversAiShell:
    def test_readme_links_ai_shell_tutorial(self):
        """README must link to the AI shell tutorial."""
        content = _README.read_text()
        assert "ai-shell-first-hour" in content

    def test_readme_mentions_sac_shell(self):
        """README must mention 'sac shell'."""
        assert "sac shell" in _README.read_text()

    def test_readme_experimental_label_for_shell(self):
        """README must mark sac shell EXPERIMENTAL."""
        content = _README.read_text()
        # Must appear near sac shell
        idx = content.lower().find("sac shell")
        assert idx >= 0, "sac shell not found in README"
        nearby = content[max(0, idx - 100): idx + 300].upper()
        assert "EXPERIMENTAL" in nearby


# ---------------------------------------------------------------------------
# Public contracts
# ---------------------------------------------------------------------------


class TestPublicContractsV49:
    def test_public_contracts_has_v49_section(self):
        """docs/public-contracts.md must have a v4.9 section."""
        content = (_DOCS / "public-contracts.md").read_text()
        assert "v4.9" in content

    def test_public_contracts_no_new_stable_contracts(self):
        """docs/public-contracts.md must state zero new stable contracts for v4.9."""
        content = (_DOCS / "public-contracts.md").read_text().lower()
        assert "zero new stable contracts" in content or "no new stable contract" in content or "adds zero new stable contracts" in content

    def test_public_contracts_experimental_label(self):
        """docs/public-contracts.md must mark v4.9 surfaces EXPERIMENTAL."""
        content = (_DOCS / "public-contracts.md").read_text()
        assert "EXPERIMENTAL" in content

    def test_public_contracts_no_v5_schedule(self):
        """docs/public-contracts.md must not schedule v5."""
        content = (_DOCS / "public-contracts.md").read_text().lower()
        assert "does not schedule v5" in content or "no v5" in content


# ---------------------------------------------------------------------------
# Versioning policy
# ---------------------------------------------------------------------------


class TestVersioningPolicyV49:
    def test_versioning_policy_has_v49_entry(self):
        """docs/versioning-policy.md must have a v4.9 changelog entry."""
        content = (_DOCS / "versioning-policy.md").read_text()
        assert "v4.9" in content

    def test_versioning_policy_no_v5_scheduled(self):
        """docs/versioning-policy.md must state no v5 is scheduled."""
        content = (_DOCS / "versioning-policy.md").read_text().lower()
        assert "no v5" in content or "does not schedule v5" in content


# ---------------------------------------------------------------------------
# MVP user guide
# ---------------------------------------------------------------------------


class TestMvpGuideV49:
    def test_mvp_guide_has_ai_shell_section(self):
        """docs/mvp-user-guide.md must have an AI shell section."""
        content = (_DOCS / "mvp-user-guide.md").read_text()
        assert "sac shell" in content

    def test_mvp_guide_experimental_label(self):
        """docs/mvp-user-guide.md must mark AI shell EXPERIMENTAL."""
        content = (_DOCS / "mvp-user-guide.md").read_text()
        assert "EXPERIMENTAL" in content

    def test_mvp_guide_no_auto_apply(self):
        """docs/mvp-user-guide.md must state no auto-apply."""
        content = (_DOCS / "mvp-user-guide.md").read_text().lower()
        assert "no auto-apply" in content or "never auto-applies" in content


# ---------------------------------------------------------------------------
# Troubleshooting
# ---------------------------------------------------------------------------


class TestTroubleshootingV49:
    def test_troubleshooting_covers_ai_shell(self):
        """docs/troubleshooting.md must cover AI shell issues."""
        content = (_DOCS / "troubleshooting.md").read_text()
        assert "AI Shell" in content or "sac shell" in content

    def test_troubleshooting_has_non_tty_entry(self):
        """docs/troubleshooting.md must cover non-TTY apply."""
        content = (_DOCS / "troubleshooting.md").read_text().lower()
        assert "non-tty" in content or "non_tty" in content


# ---------------------------------------------------------------------------
# CLI command existence
# ---------------------------------------------------------------------------


class TestShellCommandExists:
    def test_sac_shell_command_is_registered(self):
        """sac shell must be a registered command."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--help"])
        assert result.exit_code == 0

    def test_sac_smoke_ai_shell_command_is_registered(self):
        """sac smoke ai-shell must be a registered command."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["smoke", "ai-shell", "--help"])
        assert result.exit_code == 0

    def test_shell_session_state_module_importable(self):
        """shell_session package must be importable."""
        from safecode.shell_session.state import ShellSessionState, ShellTurn
        from safecode.shell_session.store import ShellSessionStore
        from safecode.shell_session.router import classify_intent, route_input
        from safecode.shell_session.overview import build_project_overview, ProjectOverview
        assert ShellSessionState is not None
        assert classify_intent is not None


# ---------------------------------------------------------------------------
# Public contract snapshots unchanged
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.subprocess
class TestPublicContractSnapshotsUnchanged:
    def test_contract_snapshots_still_pass(self):
        """Public contract snapshot tests must still pass after v4.9 changes."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_public_contract_snapshots.py", "-q", "--tb=short"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Public contract snapshots failed:\n{result.stdout}\n{result.stderr}"
        )
