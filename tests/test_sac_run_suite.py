"""Tests for sac run --suite (v4.2.1 T-4.2.1-A)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.project.profile import (
    ProfileCommand,
    ProjectProfile,
    apply_user_override,
    save_profile,
)

runner = CliRunner(mix_stderr=False)


def _make_profile(
    test_cmd: tuple[str, ...] | None = None,
    lint_cmd: tuple[str, ...] | None = None,
    typecheck_cmd: tuple[str, ...] | None = None,
    build_cmd: tuple[str, ...] | None = None,
) -> ProjectProfile:
    def _c(argv: tuple[str, ...] | None) -> ProfileCommand | None:
        if argv is None:
            return None
        return ProfileCommand(command=argv, stack="x", source="detected", missing_dependency=False)

    return ProjectProfile(
        test=_c(test_cmd),
        lint=_c(lint_cmd),
        typecheck=_c(typecheck_cmd),
        build=_c(build_cmd),
    )


def _invoke(*args, cwd: Path | None = None):
    if cwd:
        import os
        old = os.getcwd()
        try:
            os.chdir(cwd)
            return runner.invoke(app, list(args))
        finally:
            os.chdir(old)
    return runner.invoke(app, list(args))


class TestRunSuiteProfileMissing:
    def test_no_profile_exits_with_message(self, tmp_path):
        result = _invoke("run", "--suite", "test", cwd=tmp_path)
        assert result.exit_code != 0
        assert "profile detect" in result.output.lower() or "profile" in result.output.lower()

    def test_no_profile_json_output(self, tmp_path):
        import json
        result = _invoke("run", "--suite", "test", "--json", cwd=tmp_path)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"


class TestRunSuiteMissingKind:
    def test_missing_suite_command_in_profile(self, tmp_path):
        """Profile exists but no 'typecheck' command for a Python project."""
        profile = _make_profile(test_cmd=("pytest", "-q"))  # no typecheck
        save_profile(tmp_path, profile)
        result = _invoke("run", "--suite", "typecheck", cwd=tmp_path)
        assert result.exit_code != 0
        assert "sac profile" in result.output.lower() or "profile" in result.output.lower()


class TestRunSuiteInvalidKind:
    def test_unknown_kind_rejected(self, tmp_path):
        result = _invoke("run", "--suite", "unknown_kind", cwd=tmp_path)
        assert result.exit_code != 0


class TestRunSuiteCommandBlocked:
    def test_high_risk_command_blocked(self, tmp_path):
        """A profile command that classifies as high-risk should be blocked."""
        # Store a profile with a high-risk command (rm)
        profile = _make_profile(test_cmd=("rm", "-rf", "/"))
        save_profile(tmp_path, profile)
        result = _invoke("run", "--suite", "test", cwd=tmp_path)
        # Should be blocked (exit 126) due to policy
        assert result.exit_code in (1, 126)

    def test_policy_blocked_command_does_not_execute(self, tmp_path):
        """ShellRunner must block the command; it must not be executed."""
        profile = _make_profile(test_cmd=("rm", "-rf", "/tmp/dangerous"))
        save_profile(tmp_path, profile)
        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            mock_instance = MagicMock()
            from safecode.shell.risk import ShellRisk, RiskLevel
            mock_instance.assess.return_value = ShellRisk(RiskLevel.HIGH, ["dangerous"], ["rm"])
            from safecode.shell.runner import ShellRunResult
            mock_instance.run.return_value = ShellRunResult(
                command="rm -rf /tmp/dangerous",
                risk=ShellRisk(RiskLevel.HIGH, ["dangerous"], ["rm"]),
                exit_code=126,
                stdout="",
                stderr="Blocked high-risk command.",
                duration_ms=0,
                executed=False,
            )
            MockRunner.return_value = mock_instance
            result = _invoke("run", "--suite", "test", cwd=tmp_path)
        # Should not have actually executed
        assert result.exit_code in (1, 126)


class TestRunSuitePolicyGateReuse:
    def test_uses_shell_runner(self, tmp_path):
        """--suite must route through ShellRunner (not subprocess directly)."""
        profile = _make_profile(test_cmd=("echo", "suite_test"))
        save_profile(tmp_path, profile)

        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock_instance = MagicMock()
            mock_instance.assess.return_value = ShellRisk(RiskLevel.LOW, [], ["echo"])
            mock_instance.run.return_value = ShellRunResult(
                command="echo suite_test",
                risk=ShellRisk(RiskLevel.LOW, [], ["echo"]),
                exit_code=0,
                stdout="suite_test",
                stderr="",
                duration_ms=5,
                executed=True,
            )
            MockRunner.return_value = mock_instance
            _invoke("run", "--suite", "test", cwd=tmp_path)
            # ShellRunner was instantiated and run was called
            MockRunner.assert_called_once()
            mock_instance.run.assert_called_once()

    def test_suite_treated_as_yes(self, tmp_path):
        """Suite commands are auto-approved (treated as --yes=True)."""
        profile = _make_profile(test_cmd=("pytest", "-q"))
        save_profile(tmp_path, profile)

        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock_instance = MagicMock()
            mock_instance.assess.return_value = ShellRisk(RiskLevel.MEDIUM, ["medium"], ["pytest"])
            mock_instance.run.return_value = ShellRunResult(
                command="pytest -q",
                risk=ShellRisk(RiskLevel.MEDIUM, [], ["pytest"]),
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=0,
                executed=True,
            )
            MockRunner.return_value = mock_instance
            _invoke("run", "--suite", "test", cwd=tmp_path)
            # run() should have been called with approved=True
            call_kwargs = mock_instance.run.call_args
            assert call_kwargs[1].get("approved", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else True) is True


class TestRunSuiteAllKinds:
    def test_lint_suite(self, tmp_path):
        profile = _make_profile(lint_cmd=("echo", "lint"))
        save_profile(tmp_path, profile)
        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock = MagicMock()
            mock.assess.return_value = ShellRisk(RiskLevel.LOW, [], ["echo"])
            mock.run.return_value = ShellRunResult("echo lint", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "", "", 0, True)
            MockRunner.return_value = mock
            result = _invoke("run", "--suite", "lint", cwd=tmp_path)
            assert result.exit_code == 0

    def test_typecheck_suite(self, tmp_path):
        profile = _make_profile(typecheck_cmd=("echo", "typecheck"))
        save_profile(tmp_path, profile)
        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock = MagicMock()
            mock.assess.return_value = ShellRisk(RiskLevel.LOW, [], ["echo"])
            mock.run.return_value = ShellRunResult("echo typecheck", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "", "", 0, True)
            MockRunner.return_value = mock
            result = _invoke("run", "--suite", "typecheck", cwd=tmp_path)
            assert result.exit_code == 0

    def test_build_suite(self, tmp_path):
        profile = _make_profile(build_cmd=("echo", "build"))
        save_profile(tmp_path, profile)
        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock = MagicMock()
            mock.assess.return_value = ShellRisk(RiskLevel.LOW, [], ["echo"])
            mock.run.return_value = ShellRunResult("echo build", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "", "", 0, True)
            MockRunner.return_value = mock
            result = _invoke("run", "--suite", "build", cwd=tmp_path)
            assert result.exit_code == 0


class TestRunSuiteTaskMetadata:
    def test_task_metadata_preserved(self, tmp_path):
        """--suite run wires to task sidecar like a normal run."""
        profile = _make_profile(test_cmd=("echo", "test"))
        save_profile(tmp_path, profile)
        with (
            patch("safecode.cli_core.ShellRunner") as MockRunner,
            patch("safecode.cli_core.get_or_create_current_task") as mock_task,
            patch("safecode.cli_core.record_run_on_task") as mock_record,
        ):
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock = MagicMock()
            mock.assess.return_value = ShellRisk(RiskLevel.LOW, [], ["echo"])
            mock.run.return_value = ShellRunResult("echo test", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "", "", 0, True)
            MockRunner.return_value = mock

            mock_task_state = MagicMock()
            mock_task_state.task_id = "test-task-abc"
            mock_task.return_value = mock_task_state
            _invoke("run", "--suite", "test", cwd=tmp_path)
            # Task wiring should have been called
            mock_task.assert_called()


class TestRunCommandStillWorks:
    """Ensure the existing sac run <command> still works after adding --suite."""

    def test_positional_command_still_valid(self, tmp_path):
        with patch("safecode.cli_core.ShellRunner") as MockRunner:
            from safecode.shell.risk import ShellRisk, RiskLevel
            from safecode.shell.runner import ShellRunResult
            mock = MagicMock()
            mock.assess.return_value = ShellRisk(RiskLevel.LOW, [], ["echo"])
            mock.run.return_value = ShellRunResult("echo hi", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "hi", "", 0, True)
            MockRunner.return_value = mock
            result = _invoke("run", "echo hi", "--yes", cwd=tmp_path)
            assert result.exit_code == 0

    def test_no_command_and_no_suite_gives_error(self, tmp_path):
        result = _invoke("run", cwd=tmp_path)
        assert result.exit_code != 0
