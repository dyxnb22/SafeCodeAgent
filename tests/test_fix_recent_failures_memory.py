"""Tests for v4.6.1 recent failures memory in sac fix."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from safecode.cli_fix import run_fix
from safecode.memory.facade import MemoryFacade


def _make_edit_result(tmp_path: Path) -> MagicMock:
    result = MagicMock()
    result.pending_patch_path = tmp_path / ".sac" / "pending_patch.json"
    result.diff_text = "--- a/foo.py\n+++ b/foo.py\n"
    return result


def test_fix_records_recent_failure_redacted_and_capped(tmp_path: Path) -> None:
    raw = "AssertionError: token=s3cr3t assert 1 == 2"
    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = (raw, 1)
        MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
        code = run_fix(tmp_path, test_command="pytest -q")

    assert code == 0
    entries = MemoryFacade(tmp_path).read_recent_failures()
    assert len(entries) == 1
    assert entries[0]["command"] == "pytest -q"
    assert entries[0]["exit_code"] == 1
    assert "s3cr3t" not in entries[0]["tail_summary"]

    for index in range(205):
        MemoryFacade(tmp_path).record_failure(task_id=None, command=f"cmd {index}", exit_code=1, tail="tail")
    assert len(MemoryFacade(tmp_path).read_recent_failures()) == 200


def test_fix_prompt_includes_top_three_recent_failures_only(tmp_path: Path) -> None:
    facade = MemoryFacade(tmp_path)
    for index in range(4):
        facade.record_failure(task_id=f"old-{index}", command=f"old-cmd-{index}", exit_code=1, tail=f"old-tail-{index}")

    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = ("current failure", 1)
        MockOrch.return_value.edit.return_value = _make_edit_result(tmp_path)
        run_fix(tmp_path, test_command="pytest -q")

    task_text = MockOrch.return_value.edit.call_args[0][0]
    assert "Recent failure memory:" in task_text
    assert "pytest -q" in task_text
    assert "old-cmd-3" in task_text
    assert "old-cmd-2" in task_text
    assert "old-cmd-1" not in task_text
    assert "old-cmd-0" not in task_text


def test_fix_retry_from_last_failure_related_edit_flag_still_exists() -> None:
    from typer.testing import CliRunner
    from safecode.cli import app

    result = CliRunner().invoke(app, ["edit", "--help"])

    assert result.exit_code == 0
    assert "--retry-from-last-failure" in result.output
