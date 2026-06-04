"""Tests for sac fix command (v3.7.0 T-3.7.0-A)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_fix import run_fix

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_edit_result(tmp_path: Path) -> MagicMock:
    """Return a mock EditResult."""
    result = MagicMock()
    result.pending_patch_path = tmp_path / ".sac" / "pending_patch.json"
    result.diff_text = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-fail\n+pass\n"
    return result


# ---------------------------------------------------------------------------
# Unit-level tests for run_fix
# ---------------------------------------------------------------------------

class TestRunFixNoTestCommand:
    def test_error_when_no_candidates_detected(self, tmp_path: Path) -> None:
        """When no test candidates exist and no --test-command, exit 1 with error."""
        with patch("safecode.cli_fix.ProjectTestDetector") as MockDetector:
            MockDetector.return_value.detect.return_value = []
            code = run_fix(tmp_path)
        assert code == 1

    def test_uses_first_candidate_command(self, tmp_path: Path) -> None:
        """run_fix uses the first detected candidate."""
        candidate = MagicMock()
        candidate.command = "pytest -q"

        with (
            patch("safecode.cli_fix.ProjectTestDetector") as MockDetector,
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            MockDetector.return_value.detect.return_value = [candidate]
            mock_run.return_value = ("FAILED test_foo.py", 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)

            code = run_fix(tmp_path)
        assert code == 0
        mock_run.assert_called_once_with(tmp_path, "pytest -q")


class TestRunFixTestCommandOverride:
    def test_uses_provided_command(self, tmp_path: Path) -> None:
        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("error", 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
            code = run_fix(tmp_path, test_command="go test ./...")
        assert code == 0
        mock_run.assert_called_once_with(tmp_path, "go test ./...")


class TestRunFixAlreadyPassing:
    def test_exits_zero_with_nothing_to_fix(self, tmp_path: Path) -> None:
        with patch("safecode.cli_fix._run_test_command") as mock_run:
            mock_run.return_value = ("ok", 0)
            code = run_fix(tmp_path, test_command="pytest -q")
        assert code == 0

    def test_does_not_call_orchestrator_when_passing(self, tmp_path: Path) -> None:
        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("ok", 0)
            run_fix(tmp_path, test_command="pytest -q")
        MockOrch.return_value.edit.assert_not_called()


class TestRunFixEndToEnd:
    def test_calls_edit_with_redacted_context(self, tmp_path: Path) -> None:
        """The task passed to edit() must include redacted failure output (redactor runs)."""
        raw = "AssertionError: token=s3cr3t assert 1 == 2"

        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = (raw, 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
            run_fix(tmp_path, test_command="pytest -q")

        call_args = MockOrch.return_value.edit.call_args
        task_text = call_args[0][0]
        # token=<value> pattern is caught by the redactor; the raw value must not appear
        assert "s3cr3t" not in task_text

    def test_leaves_pending_patch_on_success(self, tmp_path: Path) -> None:
        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("FAILED", 1)
            er = _make_edit_result(tmp_path)
            MockOrch.return_value.edit.return_value = er
            code = run_fix(tmp_path, test_command="pytest -q")
        assert code == 0

    def test_returns_one_on_patch_error(self, tmp_path: Path) -> None:
        from safecode.patch.parser import PatchParseError

        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("FAILED", 1)
            MockOrch.return_value.edit.side_effect = PatchParseError("bad patch")
            code = run_fix(tmp_path, test_command="pytest -q")
        assert code == 1


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

class TestRunFixJsonOutput:
    def test_json_output_on_success(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        import json

        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("FAILED", 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
            run_fix(tmp_path, test_command="pytest -q", json_output=True)

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["command"] == "fix"
        assert data["status"] == "success"
        assert "pending_patch_path" in data["data"]
        assert "error" not in data

    def test_json_output_when_already_passing(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        import json

        with patch("safecode.cli_fix._run_test_command") as mock_run:
            mock_run.return_value = ("ok", 0)
            run_fix(tmp_path, test_command="pytest -q", json_output=True)

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "success"
        assert "error" not in data

    def test_json_error_on_no_candidates(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        import json

        with patch("safecode.cli_fix.ProjectTestDetector") as MockDetector:
            MockDetector.return_value.detect.return_value = []
            run_fix(tmp_path, json_output=True)

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "error"
        assert "error" in data


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestFixCLI:
    def test_fix_command_exists(self) -> None:
        result = runner.invoke(app, ["fix", "--help"])
        assert result.exit_code == 0
        assert "fix" in result.output.lower()

    def test_fix_json_flag_exists(self) -> None:
        result = runner.invoke(app, ["fix", "--help"])
        assert "--json" in result.output

    def test_fix_test_command_flag_exists(self) -> None:
        result = runner.invoke(app, ["fix", "--help"])
        assert "--test-command" in result.output

    def test_fix_watch_flags_exist(self) -> None:
        result = runner.invoke(app, ["fix", "--help"])
        assert "--watch" in result.output
        assert "--max-iterations" in result.output
        assert "--rerun-suite" in result.output

    def test_fix_exits_zero_when_tests_pass(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("safecode.cli_fix._run_test_command") as mock_run:
            mock_run.return_value = ("ok", 0)
            result = runner.invoke(
                app,
                ["fix", "--test-command", "pytest -q"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0

    def test_fix_proposes_patch_when_tests_fail(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("FAILED tests", 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
            result = runner.invoke(
                app,
                ["fix", "--test-command", "pytest -q"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# v4.2.1: fix uses profile (T-4.2.1-B)
# ---------------------------------------------------------------------------

class TestRunFixProfilePrecedence:
    """Precedence: --test-command > profile > ProjectTestDetector."""

    def test_explicit_flag_wins_over_profile(self, tmp_path: Path) -> None:
        """When --test-command is given, profile is not consulted."""
        from safecode.project.profile import ProfileCommand, ProjectProfile, save_profile
        profile = ProjectProfile(
            test=ProfileCommand(command=("profile-test",), stack="x", source="detected"),
        )
        save_profile(tmp_path, profile)

        with patch("safecode.cli_fix._run_test_command") as mock_run:
            mock_run.return_value = ("ok", 0)
            code = run_fix(tmp_path, test_command="explicit-test")

        assert code == 0
        mock_run.assert_called_once_with(tmp_path, "explicit-test")

    def test_profile_wins_over_detector(self, tmp_path: Path) -> None:
        """When profile exists with a test command, detector is not called."""
        from safecode.project.profile import ProfileCommand, ProjectProfile, save_profile
        profile = ProjectProfile(
            test=ProfileCommand(command=("profile-test", "-v"), stack="x", source="detected"),
        )
        save_profile(tmp_path, profile)

        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.ProjectTestDetector") as MockDetector,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("fail", 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
            code = run_fix(tmp_path)

        assert code == 0
        mock_run.assert_called_once_with(tmp_path, "profile-test -v")
        # Detector should not have been called
        MockDetector.return_value.detect.assert_not_called()

    def test_detector_used_when_no_profile(self, tmp_path: Path) -> None:
        """Without a profile, falls back to ProjectTestDetector as before."""
        candidate = MagicMock()
        candidate.command = "pytest -q"

        with (
            patch("safecode.cli_fix.ProjectTestDetector") as MockDetector,
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            MockDetector.return_value.detect.return_value = [candidate]
            mock_run.return_value = ("fail", 1)
            MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
            code = run_fix(tmp_path)

        assert code == 0
        mock_run.assert_called_once_with(tmp_path, "pytest -q")

    def test_profile_with_no_test_command_falls_back_to_detector(self, tmp_path: Path) -> None:
        """Profile exists but no 'test' command → fall back to detector."""
        from safecode.project.profile import ProjectProfile, save_profile
        profile = ProjectProfile()  # all commands None
        save_profile(tmp_path, profile)

        candidate = MagicMock()
        candidate.command = "detected-test"

        with (
            patch("safecode.cli_fix.ProjectTestDetector") as MockDetector,
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            MockDetector.return_value.detect.return_value = [candidate]
            mock_run.return_value = ("ok", 0)
            code = run_fix(tmp_path)

        assert code == 0
        mock_run.assert_called_once_with(tmp_path, "detected-test")

    def test_profile_override_never_auto_set_by_fix(self, tmp_path: Path) -> None:
        """sac fix must never write a user override to the profile."""
        from safecode.project.profile import load_profile

        with (
            patch("safecode.cli_fix._run_test_command") as mock_run,
            patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        ):
            mock_run.return_value = ("ok", 0)
            run_fix(tmp_path, test_command="pytest -q")

        # Profile should not have been written at all
        profile = load_profile(tmp_path)
        assert profile is None
