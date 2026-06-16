"""Tests for v4.24.2: GitHub write native tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.github_write_tools import (
    GITHUB_CREATE_PR_SPEC,
    GITHUB_PUSH_BRANCH_SPEC,
    _create_pr_handler,
    _push_branch_handler,
    _validate_branch,
    register_github_write_tools,
)
from safecode.agent.native_tools import NativeToolSpec


# ---------------------------------------------------------------------------
# _validate_branch
# ---------------------------------------------------------------------------

class TestValidateBranch:
    def test_valid_branches_pass(self):
        for name in ("main", "dev/feature-x", "fix/issue-123", "user.name"):
            assert _validate_branch(name) is None

    def test_empty_fails(self):
        assert _validate_branch("") is not None

    def test_starts_with_dash_fails(self):
        assert _validate_branch("-force") is not None

    def test_shell_injection_rejected(self):
        for bad in ("main;rm -rf /", "branch|pipe", "b && c"):
            assert _validate_branch(bad) is not None


# ---------------------------------------------------------------------------
# Tool specs — approval required
# ---------------------------------------------------------------------------

class TestGithubWriteSpecs:
    def test_create_pr_requires_approval(self):
        assert GITHUB_CREATE_PR_SPEC.requires_approval is True

    def test_push_branch_requires_approval(self):
        assert GITHUB_PUSH_BRANCH_SPEC.requires_approval is True

    def test_names(self):
        assert GITHUB_CREATE_PR_SPEC.name == "github_create_pr"
        assert GITHUB_PUSH_BRANCH_SPEC.name == "github_push_branch"

    def test_audit_event_types_stable(self):
        # v6.4.0: promoted to stable specific event types (Section 20)
        assert GITHUB_CREATE_PR_SPEC.audit_event_type == "github_pr_created"
        assert GITHUB_PUSH_BRANCH_SPEC.audit_event_type == "github_branch_pushed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocked_network():
    mock_cfg = MagicMock()
    mock_cfg.sandbox.network_enabled = False
    return patch("safecode.agent.github_write_tools._network_check", return_value="Network disabled.")


def _enabled_network():
    return patch("safecode.agent.github_write_tools._network_check", return_value=None)


# ---------------------------------------------------------------------------
# github_create_pr
# ---------------------------------------------------------------------------

class TestGithubCreatePr:
    def test_blocked_when_network_disabled(self, tmp_path):
        with _blocked_network():
            result = _create_pr_handler("c1", {
                "_project_root": str(tmp_path),
                "title": "My PR", "body": "body",
            })
        assert result.status == "blocked"

    def test_blocked_when_gh_not_available(self, tmp_path):
        with _enabled_network():
            with patch("safecode.agent.github_write_tools._gh_available", return_value=False):
                result = _create_pr_handler("c1", {
                    "_project_root": str(tmp_path),
                    "title": "My PR", "body": "body",
                })
        assert result.status == "blocked"

    def test_error_on_missing_title(self, tmp_path):
        with _enabled_network():
            with patch("safecode.agent.github_write_tools._gh_available", return_value=True):
                result = _create_pr_handler("c1", {
                    "_project_root": str(tmp_path),
                    "title": "", "body": "body",
                })
        assert result.status == "error"
        assert "title" in result.error.lower()

    def test_error_on_invalid_base_branch(self, tmp_path):
        with _enabled_network():
            with patch("safecode.agent.github_write_tools._gh_available", return_value=True):
                result = _create_pr_handler("c1", {
                    "_project_root": str(tmp_path),
                    "title": "My PR", "body": "body", "base": "-evil;rm",
                })
        assert result.status == "error"

    def test_success_with_mocked_gh(self, tmp_path):
        pr_url = "https://github.com/acme/myapp/pull/1"
        with _enabled_network():
            with patch("safecode.agent.github_write_tools._gh_available", return_value=True):
                with patch("safecode.agent.github_write_tools._run_gh", return_value=(True, pr_url)):
                    result = _create_pr_handler("c1", {
                        "_project_root": str(tmp_path),
                        "title": "My PR", "body": "body",
                    })
        assert result.status == "success"
        assert result.metadata["pr_url"] == pr_url

    def test_draft_flag_passed_to_gh(self, tmp_path):
        captured = []
        def mock_run_gh(args):
            captured.append(args)
            return True, "https://github.com/acme/myapp/pull/2"

        with _enabled_network():
            with patch("safecode.agent.github_write_tools._gh_available", return_value=True):
                with patch("safecode.agent.github_write_tools._run_gh", side_effect=mock_run_gh):
                    _create_pr_handler("c1", {
                        "_project_root": str(tmp_path),
                        "title": "Draft PR", "body": "wip", "draft": True,
                    })

        assert captured and "--draft" in captured[0]

    def test_argv_uses_list_not_shell(self, tmp_path):
        """Verify _run_gh is called with list, not a shell string."""
        captured_args = []
        def mock_run_gh(args):
            captured_args.append(args)
            return True, "https://github.com/acme/myapp/pull/3"

        with _enabled_network():
            with patch("safecode.agent.github_write_tools._gh_available", return_value=True):
                with patch("safecode.agent.github_write_tools._run_gh", side_effect=mock_run_gh):
                    _create_pr_handler("c1", {
                        "_project_root": str(tmp_path),
                        "title": "Test", "body": "",
                    })

        assert isinstance(captured_args[0], list)


# ---------------------------------------------------------------------------
# github_push_branch
# ---------------------------------------------------------------------------

class TestGithubPushBranch:
    def test_blocked_when_network_disabled(self, tmp_path):
        with _blocked_network():
            result = _push_branch_handler("c1", {"_project_root": str(tmp_path)})
        assert result.status == "blocked"

    def test_error_on_invalid_branch_name(self, tmp_path):
        with _enabled_network():
            with patch("safecode.agent.github_write_tools.shutil.which", return_value="/usr/bin/git"):
                result = _push_branch_handler("c1", {
                    "_project_root": str(tmp_path),
                    "branch": "-evil;rm -rf /",
                })
        assert result.status == "error"

    def test_success_with_mocked_git(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Branch pushed"
        mock_result.stderr = ""

        with _enabled_network():
            with patch("safecode.agent.github_write_tools.shutil.which", return_value="/usr/bin/git"):
                with patch("subprocess.run", return_value=mock_result):
                    result = _push_branch_handler("c1", {
                        "_project_root": str(tmp_path),
                        "branch": "dev/feature-x",
                    })

        assert result.status == "success"
        assert result.metadata["branch"] == "dev/feature-x"
        assert result.metadata["force"] is False

    def test_force_flag_passed_to_git(self, tmp_path):
        """Verify --force is passed when force=True (on a non-protected branch)."""
        captured = []
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        def mock_run(args, **kwargs):
            captured.append(args)
            return mock_result

        with _enabled_network():
            with patch("safecode.agent.github_write_tools.shutil.which", return_value="/usr/bin/git"):
                with patch("safecode.agent.github_write_tools._get_current_branch", return_value="feature/fix"):
                    with patch("subprocess.run", side_effect=mock_run):
                        _push_branch_handler("c1", {
                            "_project_root": str(tmp_path),
                            "branch": "feature/fix", "force": True,
                        })

        assert captured and "--force" in captured[0]

    def test_git_argv_shell_false(self, tmp_path):
        """subprocess.run must not use shell=True."""
        captured_kwargs: list[dict] = []
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        def mock_run(args, **kwargs):
            captured_kwargs.append(kwargs)
            return mock_result

        with _enabled_network():
            with patch("safecode.agent.github_write_tools.shutil.which", return_value="/usr/bin/git"):
                with patch("subprocess.run", side_effect=mock_run):
                    _push_branch_handler("c1", {"_project_root": str(tmp_path)})

        assert not captured_kwargs[0].get("shell", False)


# ---------------------------------------------------------------------------
# register_github_write_tools
# ---------------------------------------------------------------------------

class TestRegisterGithubWriteTools:
    def test_registers_both_tools(self, tmp_path):
        from safecode.agent.native_dispatcher import NativeToolDispatcher
        dispatcher = NativeToolDispatcher()
        register_github_write_tools(dispatcher, tmp_path)
        names = {s.name for s in dispatcher.specs()}
        assert "github_create_pr" in names
        assert "github_push_branch" in names
