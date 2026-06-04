"""Tests for v4.3 sac fix --watch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from safecode.cli_fix import run_fix_watch
from safecode.project.profile import ProfileCommand, ProjectProfile, save_profile
from safecode.shell.risk import RiskLevel, ShellRisk
from safecode.shell.runner import ShellRunResult
from safecode.task.store import TaskStore
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


def _edit_result(tmp_path: Path, patch_id: str = "patch-watch") -> MagicMock:
    result = MagicMock()
    result.pending_patch_path = tmp_path / ".sac" / "pending_patch.json"
    result.diff_text = "--- a/foo.py\n+++ b/foo.py\n"
    result.proposal.id = patch_id
    return result


def test_watch_first_failure_proposes_pending_patch(tmp_path: Path) -> None:
    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = ("FAILED", 1)
        MockOrch.return_value.edit.return_value = _edit_result(tmp_path)
        code = run_fix_watch(tmp_path, test_command="pytest -q")

    assert code == 0
    MockOrch.return_value.edit.assert_called_once()
    state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
    assert state is not None
    iteration = state.iterations[-1]
    assert iteration.mode == "watch"
    assert iteration.suite == "test"
    assert iteration.status == "proposed"
    assert iteration.pending_patch_path.endswith("pending_patch.json")


def test_watch_pass_after_rerun_marks_task_applied(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    state = store.create("rerun")

    with patch("safecode.cli_fix._run_test_command") as mock_run:
        mock_run.return_value = ("ok", 0)
        code = run_fix_watch(tmp_path, test_command="pytest -q")

    assert code == 0
    loaded = store.load(state.task_id)
    assert loaded is not None
    assert loaded.status == "applied"
    assert loaded.iterations[-1].status == "passed"


def test_watch_max_iterations_stops_without_edit(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    state = store.create("max")
    from safecode.task.wiring import record_fix_on_task

    record_fix_on_task(tmp_path, state.task_id, "pytest -q", 1, "old", mode="watch", status="proposed")

    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = ("FAILED again", 1)
        code = run_fix_watch(tmp_path, test_command="pytest -q", max_iterations=1)

    assert code == 1
    MockOrch.return_value.edit.assert_not_called()
    loaded = store.load(state.task_id)
    assert loaded is not None
    assert loaded.iterations[-1].status == "failed"


def test_watch_json_shape(tmp_path: Path, capsys) -> None:
    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = ("FAILED", 1)
        MockOrch.return_value.edit.return_value = _edit_result(tmp_path)
        run_fix_watch(tmp_path, test_command="pytest -q", json_output=True)

    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert payload["command"] == "fix"
    assert payload["status"] == "success"
    assert data["task_id"]
    assert data["iteration_index"] == 0
    assert data["test_command"] == "pytest -q"
    assert data["test_exit_code"] == 1
    assert data["pending_patch_path"].endswith("pending_patch.json")
    assert "sac apply" in data["next_step"]


def test_watch_never_auto_applies(tmp_path: Path) -> None:
    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = ("FAILED", 1)
        orch = MockOrch.return_value
        orch.edit.return_value = _edit_result(tmp_path)
        code = run_fix_watch(tmp_path, test_command="pytest -q")

    assert code == 0
    orch.edit.assert_called_once()
    orch.apply.assert_not_called()
    assert not (tmp_path / ".sac" / "checkpoints").exists()


def test_watch_flags_are_registered() -> None:
    result = runner.invoke(app, ["fix", "--help"])
    assert result.exit_code == 0
    assert "--watch" in result.output
    assert "--max-iterations" in result.output
    assert "--rerun-suite" in result.output
    assert "--timeout-seconds" in result.output


def _profile_command(argv: tuple[str, ...]) -> ProfileCommand:
    return ProfileCommand(command=argv, stack="x", source="detected", missing_dependency=False)


def test_timeout_records_command_timeout(tmp_path: Path) -> None:
    with patch("safecode.cli_fix._run_test_command") as mock_run:
        mock_run.return_value = ("Test command timed out.", 124)
        code = run_fix_watch(tmp_path, test_command="pytest -q", timeout_seconds=7)

    assert code == 124
    state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
    assert state is not None
    assert state.iterations[-1].test_exit_code == 124
    assert state.iterations[-1].failure_category == "command_timeout"


def test_rerun_suite_all_uses_profile_order(tmp_path: Path) -> None:
    profile = ProjectProfile(
        test=_profile_command(("echo", "test")),
        lint=_profile_command(("echo", "lint")),
        typecheck=_profile_command(("echo", "typecheck")),
        build=_profile_command(("echo", "build")),
    )
    save_profile(tmp_path, profile)

    with patch("safecode.cli_fix.ShellRunner") as MockRunner:
        mock = MagicMock()
        mock.run.return_value = ShellRunResult("echo ok", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "ok", "", 1, True)
        MockRunner.return_value = mock
        code = run_fix_watch(tmp_path, rerun_suite="all", timeout_seconds=9)

    assert code == 0
    assert [call.args[0] for call in mock.run.call_args_list] == [
        "echo test",
        "echo lint",
        "echo typecheck",
        "echo build",
    ]
    assert all(call.kwargs["approved"] is True for call in mock.run.call_args_list)
    assert all(call.kwargs["timeout_seconds"] == 9 for call in mock.run.call_args_list)


def test_rerun_suite_all_skips_missing_suites(tmp_path: Path, capsys) -> None:
    profile = ProjectProfile(test=_profile_command(("echo", "test")))
    save_profile(tmp_path, profile)

    with patch("safecode.cli_fix.ShellRunner") as MockRunner:
        mock = MagicMock()
        mock.run.return_value = ShellRunResult("echo test", ShellRisk(RiskLevel.LOW, [], ["echo"]), 0, "ok", "", 1, True)
        MockRunner.return_value = mock
        run_fix_watch(tmp_path, rerun_suite="all", json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["data"]["skipped_suites"] == ["lint", "typecheck", "build"]
    mock.run.assert_called_once()


def test_rerun_suite_all_blocked_command_stops(tmp_path: Path) -> None:
    profile = ProjectProfile(test=_profile_command(("rm", "-rf", "/tmp/nope")))
    save_profile(tmp_path, profile)

    with (
        patch("safecode.cli_fix.ShellRunner") as MockRunner,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock = MagicMock()
        mock.run.return_value = ShellRunResult(
            "rm -rf /tmp/nope",
            ShellRisk(RiskLevel.HIGH, ["danger"], ["rm"]),
            126,
            "",
            "Blocked high-risk command.",
            0,
            False,
        )
        MockRunner.return_value = mock
        code = run_fix_watch(tmp_path, rerun_suite="all")

    assert code == 126
    MockOrch.return_value.edit.assert_not_called()
    state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
    assert state is not None
    assert state.iterations[-1].failure_category == "blocked_suite_command"
