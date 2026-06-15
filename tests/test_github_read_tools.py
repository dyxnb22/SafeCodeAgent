"""Tests for v4.24.1: GitHub read-only native tools."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest

from safecode.agent.github_read_tools import (
    GITHUB_READ_FILE_SPEC,
    GITHUB_READ_ISSUE_SPEC,
    GITHUB_READ_PR_SPEC,
    _validate_gh_name,
    register_github_read_tools,
    _read_issue_handler,
    _read_pr_handler,
    _read_file_handler,
)
from safecode.agent.native_tools import NativeToolSpec


# ---------------------------------------------------------------------------
# _validate_gh_name
# ---------------------------------------------------------------------------

class TestValidateGhName:
    def test_valid_names_pass(self):
        for name in ("owner", "my-repo", "Org123", "user.name", "a_b"):
            assert _validate_gh_name(name, "owner") is None

    def test_empty_name_fails(self):
        assert _validate_gh_name("", "owner") is not None

    def test_shell_injection_rejected(self):
        for bad in ("owner;ls", "owner|cat", "owner && rm -rf /", "owner`id`"):
            assert _validate_gh_name(bad, "owner") is not None

    def test_path_traversal_rejected(self):
        assert _validate_gh_name("../etc", "owner") is not None


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

class TestGithubReadSpecs:
    def test_all_are_native_tool_specs(self):
        for spec in (GITHUB_READ_ISSUE_SPEC, GITHUB_READ_PR_SPEC, GITHUB_READ_FILE_SPEC):
            assert isinstance(spec, NativeToolSpec)

    def test_all_read_only(self):
        for spec in (GITHUB_READ_ISSUE_SPEC, GITHUB_READ_PR_SPEC, GITHUB_READ_FILE_SPEC):
            assert spec.requires_approval is False
            assert spec.audit_event_type == "tool_call_read"

    def test_names(self):
        assert GITHUB_READ_ISSUE_SPEC.name == "github_read_issue"
        assert GITHUB_READ_PR_SPEC.name == "github_read_pr"
        assert GITHUB_READ_FILE_SPEC.name == "github_read_file"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocked_network_patch():
    """Patch SafeCodeConfig to return network_enabled=False."""
    from unittest.mock import MagicMock
    mock_cfg = MagicMock()
    mock_cfg.sandbox.network_enabled = False
    return patch("safecode.agent.github_read_tools.SafeCodeConfig.load", return_value=mock_cfg)


def _enabled_network_patch():
    """Patch SafeCodeConfig to return network_enabled=True."""
    from unittest.mock import MagicMock
    mock_cfg = MagicMock()
    mock_cfg.sandbox.network_enabled = True
    return patch("safecode.agent.github_read_tools.SafeCodeConfig.load", return_value=mock_cfg)


# ---------------------------------------------------------------------------
# github_read_issue
# ---------------------------------------------------------------------------

class TestGithubReadIssue:
    def test_blocked_when_network_disabled(self, tmp_path):
        with _blocked_network_patch():
            result = _read_issue_handler("c1", {
                "_project_root": str(tmp_path),
                "owner": "acme", "repo": "myapp", "issue": 42,
            })
        assert result.status == "blocked"

    def test_blocked_when_gh_not_available(self, tmp_path):
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=False):
                result = _read_issue_handler("c1", {
                    "_project_root": str(tmp_path),
                    "owner": "acme", "repo": "myapp", "issue": 42,
                })
        assert result.status == "blocked"

    def test_error_on_invalid_owner(self, tmp_path):
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                result = _read_issue_handler("c1", {
                    "_project_root": str(tmp_path),
                    "owner": "evil;rm -rf", "repo": "myapp", "issue": 1,
                })
        assert result.status == "error"

    def test_error_on_invalid_issue_number(self, tmp_path):
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                result = _read_issue_handler("c1", {
                    "_project_root": str(tmp_path),
                    "owner": "acme", "repo": "myapp", "issue": "not-a-number",
                })
        assert result.status == "error"

    def test_success_with_mocked_gh(self, tmp_path):
        fake_output = json.dumps({"title": "Test issue", "body": "body text", "state": "OPEN", "number": 42})
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                with patch("safecode.agent.github_read_tools._run_gh", return_value=(True, fake_output)):
                    result = _read_issue_handler("c1", {
                        "_project_root": str(tmp_path),
                        "owner": "acme", "repo": "myapp", "issue": 42,
                    })
        assert result.status == "success"
        assert "Test issue" in result.output

    def test_gh_argv_uses_list_not_shell(self, tmp_path):
        """Verify subprocess.run is called with shell=False (list argv)."""
        captured = []

        def mock_run(args, **kwargs):
            captured.append((args, kwargs))
            from unittest.mock import MagicMock
            r = MagicMock()
            r.returncode = 0
            r.stdout = '{"title":"x","body":"","state":"OPEN","number":1}'
            r.stderr = ""
            return r

        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                with patch("subprocess.run", side_effect=mock_run):
                    _read_issue_handler("c1", {
                        "_project_root": str(tmp_path),
                        "owner": "acme", "repo": "myapp", "issue": 1,
                    })

        assert captured, "subprocess.run was not called"
        args, kwargs = captured[0]
        assert isinstance(args, list), "argv must be a list (shell=False)"
        assert kwargs.get("shell", False) is False


# ---------------------------------------------------------------------------
# github_read_pr
# ---------------------------------------------------------------------------

class TestGithubReadPr:
    def test_blocked_when_network_disabled(self, tmp_path):
        with _blocked_network_patch():
            result = _read_pr_handler("c1", {
                "_project_root": str(tmp_path),
                "owner": "acme", "repo": "myapp", "pr": 7,
            })
        assert result.status == "blocked"

    def test_success_with_mocked_gh(self, tmp_path):
        fake_output = json.dumps({"title": "My PR", "body": "pr body", "state": "OPEN", "number": 7})
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                with patch("safecode.agent.github_read_tools._run_gh", return_value=(True, fake_output)):
                    result = _read_pr_handler("c1", {
                        "_project_root": str(tmp_path),
                        "owner": "acme", "repo": "myapp", "pr": 7,
                    })
        assert result.status == "success"
        assert "My PR" in result.output


# ---------------------------------------------------------------------------
# github_read_file
# ---------------------------------------------------------------------------

class TestGithubReadFile:
    def test_blocked_when_network_disabled(self, tmp_path):
        with _blocked_network_patch():
            result = _read_file_handler("c1", {
                "_project_root": str(tmp_path),
                "owner": "acme", "repo": "myapp", "path": "README.md",
            })
        assert result.status == "blocked"

    def test_blocked_on_path_traversal(self, tmp_path):
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                result = _read_file_handler("c1", {
                    "_project_root": str(tmp_path),
                    "owner": "acme", "repo": "myapp", "path": "../../etc/passwd",
                })
        assert result.status == "blocked"

    def test_success_decodes_base64_content(self, tmp_path):
        file_content = "Hello, world!\n"
        encoded = base64.b64encode(file_content.encode()).decode()
        fake_output = json.dumps({"content": encoded, "name": "README.md"})
        with _enabled_network_patch():
            with patch("safecode.agent.github_read_tools._gh_available", return_value=True):
                with patch("safecode.agent.github_read_tools._run_gh", return_value=(True, fake_output)):
                    result = _read_file_handler("c1", {
                        "_project_root": str(tmp_path),
                        "owner": "acme", "repo": "myapp", "path": "README.md",
                    })
        assert result.status == "success"
        assert "Hello, world!" in result.output


# ---------------------------------------------------------------------------
# register_github_read_tools
# ---------------------------------------------------------------------------

class TestRegisterGithubReadTools:
    def test_registers_all_three_tools(self, tmp_path):
        from safecode.agent.native_dispatcher import NativeToolDispatcher
        dispatcher = NativeToolDispatcher()
        register_github_read_tools(dispatcher, tmp_path)
        names = {s.name for s in dispatcher.specs()}
        assert "github_read_issue" in names
        assert "github_read_pr" in names
        assert "github_read_file" in names
