"""Tests for GitHub PR stable contract (v6.4.0 — Section 20).

All tests use mocked subprocess / gh CLI so no real network calls are made.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.github_write_tools import (
    GITHUB_CREATE_PR_SPEC,
    GITHUB_PUSH_BRANCH_SPEC,
    PROTECTED_BRANCHES,
    _build_pr_footer,
    _create_pr_handler,
    _get_current_branch,
    _push_branch_handler,
    _validate_branch,
)


# ---------------------------------------------------------------------------
# Protected branches constant
# ---------------------------------------------------------------------------


class TestProtectedBranches:
    def test_main_is_protected(self) -> None:
        assert "main" in PROTECTED_BRANCHES

    def test_master_is_protected(self) -> None:
        assert "master" in PROTECTED_BRANCHES

    def test_trunk_is_protected(self) -> None:
        assert "trunk" in PROTECTED_BRANCHES

    def test_feature_branch_not_protected(self) -> None:
        assert "feature/my-feature" not in PROTECTED_BRANCHES

    def test_is_frozenset(self) -> None:
        assert isinstance(PROTECTED_BRANCHES, frozenset)


# ---------------------------------------------------------------------------
# Audit event types — stable contract invariant
# ---------------------------------------------------------------------------


class TestStableAuditEventTypes:
    def test_create_pr_audit_type_is_github_pr_created(self) -> None:
        assert GITHUB_CREATE_PR_SPEC.audit_event_type == "github_pr_created"

    def test_push_branch_audit_type_is_github_branch_pushed(self) -> None:
        assert GITHUB_PUSH_BRANCH_SPEC.audit_event_type == "github_branch_pushed"

    def test_both_require_approval(self) -> None:
        assert GITHUB_CREATE_PR_SPEC.requires_approval is True
        assert GITHUB_PUSH_BRANCH_SPEC.requires_approval is True


# ---------------------------------------------------------------------------
# github_push_branch: protected branch structural gate
# ---------------------------------------------------------------------------


class TestPushBranchProtectedGate:
    """Structural block on protected branches — cannot be bypassed."""

    def _inp(self, branch: str, **kwargs) -> dict:
        return {"_project_root": "/tmp", "branch": branch, **kwargs}

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_main_blocked(self, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "main"}
        result = _push_branch_handler("c1", inp)
        assert result.status == "blocked"
        assert "main" in (result.error or "")
        assert "not allowed" in (result.error or "")

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_master_blocked(self, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "master"}
        result = _push_branch_handler("c2", inp)
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_trunk_blocked(self, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "trunk"}
        result = _push_branch_handler("c3", inp)
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="main")
    def test_implicit_main_branch_blocked(self, _branch, _which, _net, tmp_path: Path) -> None:
        """Even without explicit branch arg, if HEAD is main it must be blocked."""
        inp = {"_project_root": str(tmp_path)}  # no branch arg → resolves to current
        result = _push_branch_handler("c4", inp)
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="dev/feature-x")
    def test_feature_branch_not_blocked_by_gate(self, _branch, _which, _net, tmp_path: Path) -> None:
        """Feature branches should not be blocked by the protected gate."""
        inp = {"_project_root": str(tmp_path), "branch": "dev/feature-x", "dry_run": True}
        result = _push_branch_handler("c5", inp)
        assert result.status == "success"
        assert "DRY RUN" in (result.output or "")

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_block_message_mentions_feature_branch(self, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "main"}
        result = _push_branch_handler("c6", inp)
        assert "feature branch" in (result.error or "").lower() or "create" in (result.error or "").lower()

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_block_message_says_cannot_be_overridden(self, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "master"}
        result = _push_branch_handler("c7", inp)
        assert "cannot be overridden" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# github_push_branch: dry_run
# ---------------------------------------------------------------------------


class TestPushBranchDryRun:
    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/auth")
    def test_dry_run_returns_success_without_git_call(self, _branch, _which, _net, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            inp = {"_project_root": str(tmp_path), "branch": "feature/auth", "dry_run": True}
            result = _push_branch_handler("c8", inp)
            assert result.status == "success"
            assert "DRY RUN" in (result.output or "")
            mock_run.assert_not_called()

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/x")
    def test_dry_run_metadata_has_dry_run_true(self, _branch, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "feature/x", "dry_run": True}
        result = _push_branch_handler("c9", inp)
        assert result.metadata.get("dry_run") is True


# ---------------------------------------------------------------------------
# github_push_branch: existing invariants preserved
# ---------------------------------------------------------------------------


class TestPushBranchExistingInvariants:
    @patch("safecode.agent.github_write_tools._network_check", return_value="network disabled")
    def test_blocked_when_network_disabled(self, _net, tmp_path: Path) -> None:
        result = _push_branch_handler("c10", {"_project_root": str(tmp_path)})
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value=None)
    def test_blocked_when_git_not_found(self, _which, _net, tmp_path: Path) -> None:
        result = _push_branch_handler("c11", {"_project_root": str(tmp_path)})
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_invalid_branch_name_rejected(self, _which, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "branch": "bad;branch"}
        result = _push_branch_handler("c12", inp)
        assert result.status == "error"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/y")
    def test_success_with_mocked_git(self, _branch, _which, _net, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Branch pushed."
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            inp = {"_project_root": str(tmp_path), "branch": "feature/y"}
            result = _push_branch_handler("c13", inp)
        assert result.status == "success"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/z")
    def test_git_argv_uses_shell_false(self, _branch, _which, _net, tmp_path: Path) -> None:
        """subprocess.run must be called with shell=False (no shell injection)."""
        captured: list[dict] = []
        def fake_run(args, **kwargs):
            captured.append(kwargs)
            m = MagicMock(); m.returncode = 0; m.stdout = "ok"; m.stderr = ""
            return m
        with patch("subprocess.run", side_effect=fake_run):
            inp = {"_project_root": str(tmp_path), "branch": "feature/z"}
            _push_branch_handler("c14", inp)
        assert captured, "subprocess.run not called"
        assert captured[0].get("shell") is False or "shell" not in captured[0]


# ---------------------------------------------------------------------------
# github_create_pr: PR body footer
# ---------------------------------------------------------------------------


class TestCreatePrBodyFooter:
    def test_footer_always_appended(self, tmp_path: Path) -> None:
        footer = _build_pr_footer(tmp_path, "feature/auth")
        assert "SafeCode Audit Reference" in footer
        assert "feature/auth" in footer
        assert "Checkpoint" in footer

    def test_footer_contains_timestamp(self, tmp_path: Path) -> None:
        footer = _build_pr_footer(tmp_path, "fix/bug")
        assert "Created:" in footer

    def test_footer_contains_tool_name(self, tmp_path: Path) -> None:
        footer = _build_pr_footer(tmp_path, "feat/x")
        assert "github_create_pr" in footer

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/auth")
    def test_dry_run_body_contains_footer(self, _branch, _gh, _net, tmp_path: Path) -> None:
        inp = {
            "_project_root": str(tmp_path),
            "title": "Fix auth",
            "body": "This PR fixes auth.",
            "dry_run": True,
        }
        result = _create_pr_handler("c20", inp)
        assert result.status == "success"
        assert "SafeCode Audit Reference" in (result.output or "")

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/auth")
    @patch("safecode.agent.github_write_tools._run_gh")
    def test_enriched_body_sent_to_gh(self, mock_run_gh, _branch, _gh, _net, tmp_path: Path) -> None:
        """The enriched body (with footer) must be what's sent to gh pr create."""
        mock_run_gh.return_value = (True, "https://github.com/owner/repo/pull/1")
        inp = {
            "_project_root": str(tmp_path),
            "title": "My PR",
            "body": "User description.",
        }
        _create_pr_handler("c21", inp)
        assert mock_run_gh.called
        args = mock_run_gh.call_args[0][0]
        body_idx = args.index("--body") + 1
        sent_body = args[body_idx]
        assert "SafeCode Audit Reference" in sent_body
        assert "User description." in sent_body


# ---------------------------------------------------------------------------
# github_create_pr: dry_run
# ---------------------------------------------------------------------------


class TestCreatePrDryRun:
    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/x")
    def test_dry_run_does_not_call_gh(self, _branch, _gh, _net, tmp_path: Path) -> None:
        with patch("safecode.agent.github_write_tools._run_gh") as mock_gh:
            inp = {"_project_root": str(tmp_path), "title": "T", "body": "B", "dry_run": True}
            result = _create_pr_handler("c22", inp)
            assert result.status == "success"
            mock_gh.assert_not_called()

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/x")
    def test_dry_run_metadata_has_dry_run_true(self, _branch, _gh, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "title": "T", "body": "B", "dry_run": True}
        result = _create_pr_handler("c23", inp)
        assert result.metadata.get("dry_run") is True


# ---------------------------------------------------------------------------
# github_create_pr: existing invariants preserved
# ---------------------------------------------------------------------------


class TestCreatePrExistingInvariants:
    @patch("safecode.agent.github_write_tools._network_check", return_value="network disabled")
    def test_blocked_when_network_disabled(self, _net, tmp_path: Path) -> None:
        result = _create_pr_handler("c30", {"_project_root": str(tmp_path), "title": "T", "body": "B"})
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=False)
    def test_blocked_when_gh_not_found(self, _gh, _net, tmp_path: Path) -> None:
        result = _create_pr_handler("c31", {"_project_root": str(tmp_path), "title": "T", "body": "B"})
        assert result.status == "blocked"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    def test_error_on_missing_title(self, _gh, _net, tmp_path: Path) -> None:
        result = _create_pr_handler("c32", {"_project_root": str(tmp_path), "body": "B"})
        assert result.status == "error"
        assert "title" in (result.error or "").lower()

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    def test_error_on_invalid_base_branch(self, _gh, _net, tmp_path: Path) -> None:
        inp = {"_project_root": str(tmp_path), "title": "T", "body": "B", "base": "bad;base"}
        result = _create_pr_handler("c33", inp)
        assert result.status == "error"

    @patch("safecode.agent.github_write_tools._network_check", return_value=None)
    @patch("safecode.agent.github_write_tools._gh_available", return_value=True)
    @patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/ok")
    @patch("safecode.agent.github_write_tools._run_gh")
    def test_success_returns_pr_url(self, mock_run_gh, _branch, _gh, _net, tmp_path: Path) -> None:
        mock_run_gh.return_value = (True, "https://github.com/owner/repo/pull/42")
        inp = {"_project_root": str(tmp_path), "title": "My PR", "body": "Description."}
        result = _create_pr_handler("c34", inp)
        assert result.status == "success"
        assert "github.com" in (result.output or "")


# ---------------------------------------------------------------------------
# Spec schema: dry_run field present
# ---------------------------------------------------------------------------


class TestSpecSchema:
    def test_create_pr_spec_has_dry_run(self) -> None:
        props = GITHUB_CREATE_PR_SPEC.input_schema.get("properties", {})
        assert "dry_run" in props

    def test_push_branch_spec_has_dry_run(self) -> None:
        props = GITHUB_PUSH_BRANCH_SPEC.input_schema.get("properties", {})
        assert "dry_run" in props

    def test_push_branch_spec_description_mentions_protected(self) -> None:
        desc = GITHUB_PUSH_BRANCH_SPEC.description
        assert "main" in desc.lower() or "protected" in desc.lower() or "blocked" in desc.lower()
