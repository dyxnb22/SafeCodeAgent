"""Tests for v4.8.0 T-4.8.0-A smoke-shell-first.

Verifies:
- The smoke suite CLI command exists and is callable.
- Each scenario can be invoked individually.
- JSON output shape is correct.
- All 8 scenarios are registered.
- The suite runs deterministically under mock provider (no real network).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_smoke import (
    ScenarioResult,
    SmokeRunResult,
    _SCENARIOS,
    run_shell_first_smoke,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Scenario registry tests
# ---------------------------------------------------------------------------


class TestScenarioRegistry:
    def test_eight_scenarios_registered(self):
        assert len(_SCENARIOS) == 8

    def test_scenario_names_are_unique(self):
        names = [name for name, _ in _SCENARIOS]
        assert len(names) == len(set(names))

    def test_expected_scenario_names_present(self):
        names = {name for name, _ in _SCENARIOS}
        expected = {
            "docs-edit-task",
            "failing-test-repair-with-fix-watch",
            "command-profile-detection",
            "dirty-tree-refusal",
            "rollback-after-commit-warn",
            "resume-after-sigint",
            "debug-bundle-redaction",
            "pinned-files-in-context",
        }
        assert names == expected

    def test_all_scenario_fns_callable(self):
        for name, fn in _SCENARIOS:
            assert callable(fn), f"scenario {name!r} fn must be callable"


# ---------------------------------------------------------------------------
# SmokeRunResult model
# ---------------------------------------------------------------------------


class TestSmokeRunResult:
    def test_empty_result(self):
        result = SmokeRunResult()
        assert result.passed == 0
        assert result.failed == 0
        assert result.all_passed is True

    def test_all_pass(self):
        result = SmokeRunResult(
            scenarios=[
                ScenarioResult("a", True, "ok", 10),
                ScenarioResult("b", True, "ok", 20),
            ]
        )
        assert result.passed == 2
        assert result.failed == 0
        assert result.all_passed is True

    def test_partial_fail(self):
        result = SmokeRunResult(
            scenarios=[
                ScenarioResult("a", True, "ok", 10),
                ScenarioResult("b", False, "assertion failed", 20),
            ]
        )
        assert result.passed == 1
        assert result.failed == 1
        assert result.all_passed is False

    def test_to_dict_shape(self):
        result = SmokeRunResult(
            scenarios=[ScenarioResult("x", True, "ok", 5)]
        )
        d = result.to_dict()
        assert d["passed"] == 1
        assert d["failed"] == 0
        assert d["total"] == 1
        assert d["all_passed"] is True
        assert len(d["scenarios"]) == 1
        scenario_d = d["scenarios"][0]
        assert scenario_d["name"] == "x"
        assert scenario_d["passed"] is True
        assert scenario_d["message"] == "ok"
        assert "duration_ms" in scenario_d


# ---------------------------------------------------------------------------
# CLI invocation tests
# ---------------------------------------------------------------------------


class TestSmokeCliCommand:
    def test_smoke_help_accessible(self):
        result = runner.invoke(app, ["smoke", "--help"])
        assert result.exit_code == 0

    def test_smoke_shell_first_help_accessible(self):
        result = runner.invoke(app, ["smoke", "shell-first", "--help"])
        assert result.exit_code == 0
        assert "shell-first" in result.output.lower() or "smoke" in result.output.lower()

    def test_smoke_shell_first_has_json_option(self):
        result = runner.invoke(app, ["smoke", "shell-first", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_smoke_shell_first_has_only_option(self):
        result = runner.invoke(app, ["smoke", "shell-first", "--help"])
        assert result.exit_code == 0
        assert "--only" in result.output

    def test_smoke_shell_first_json_output_shape(self):
        """JSON output must have command/status/data fields."""
        with patch("safecode.cli_smoke.run_shell_first_smoke") as mock_run:
            mock_run.return_value = SmokeRunResult(
                scenarios=[ScenarioResult("docs-edit-task", True, "ok", 5)]
            )
            result = runner.invoke(app, ["smoke", "shell-first", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["command"] == "smoke shell-first"
        assert data["status"] in {"pass", "fail"}
        assert "data" in data
        assert "scenarios" in data["data"]
        assert "passed" in data["data"]
        assert "failed" in data["data"]
        assert "all_passed" in data["data"]

    def test_smoke_shell_first_json_status_pass_when_all_pass(self):
        with patch("safecode.cli_smoke.run_shell_first_smoke") as mock_run:
            mock_run.return_value = SmokeRunResult(
                scenarios=[ScenarioResult("docs-edit-task", True, "ok", 5)]
            )
            result = runner.invoke(app, ["smoke", "shell-first", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "pass"

    def test_smoke_shell_first_json_status_fail_when_any_fail(self):
        with patch("safecode.cli_smoke.run_shell_first_smoke") as mock_run:
            mock_run.return_value = SmokeRunResult(
                scenarios=[ScenarioResult("docs-edit-task", False, "broke", 5)]
            )
            result = runner.invoke(app, ["smoke", "shell-first", "--json"])
        data = json.loads(result.output)
        assert data["status"] == "fail"

    def test_smoke_shell_first_exit_0_on_pass(self):
        with patch("safecode.cli_smoke.run_shell_first_smoke") as mock_run:
            mock_run.return_value = SmokeRunResult(
                scenarios=[ScenarioResult("docs-edit-task", True, "ok", 5)]
            )
            result = runner.invoke(app, ["smoke", "shell-first", "--json"])
        assert result.exit_code == 0

    def test_smoke_shell_first_exit_1_on_fail(self):
        with patch("safecode.cli_smoke.run_shell_first_smoke") as mock_run:
            mock_run.return_value = SmokeRunResult(
                scenarios=[ScenarioResult("docs-edit-task", False, "broke", 5)]
            )
            result = runner.invoke(app, ["smoke", "shell-first", "--json"])
        assert result.exit_code == 1

    def test_smoke_not_visible_in_root_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "smoke" not in result.output.split("Commands")[1].split()[::2]


# ---------------------------------------------------------------------------
# run_shell_first_smoke function tests
# ---------------------------------------------------------------------------


class TestRunShellFirstSmoke:
    def test_only_filter_works(self):
        result = run_shell_first_smoke(only=["docs-edit-task"])
        assert len(result.scenarios) == 1
        assert result.scenarios[0].name == "docs-edit-task"

    def test_only_empty_after_filter(self):
        result = run_shell_first_smoke(only=["nonexistent-scenario"])
        assert len(result.scenarios) == 0

    def test_none_only_runs_all(self):
        with patch("safecode.cli_smoke._run_scenario") as mock_run:
            mock_run.return_value = ScenarioResult("x", True, "ok", 1)
            result = run_shell_first_smoke(only=None)
        assert len(result.scenarios) == 8

    def test_scenario_result_is_frozen(self):
        s = ScenarioResult("name", True, "ok", 5)
        with pytest.raises((AttributeError, TypeError)):
            s.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Individual scenario tests (using mock provider only)
# ---------------------------------------------------------------------------


class TestScenarioDocsEditTask:
    def test_passes_with_temp_dir(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_docs_edit_task
        _scenario_docs_edit_task(tmp_path)

    def test_creates_task_in_open_status(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_docs_edit_task
        from safecode.task.store import TaskStore
        _scenario_docs_edit_task(tmp_path)
        store = TaskStore(tmp_path)
        current_id = store.current_id()
        assert current_id is not None


class TestScenarioCommandProfileDetection:
    def test_detects_pytest_in_python_project(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_command_profile_detection
        _scenario_command_profile_detection(tmp_path)


class TestScenarioDirtyTreeRefusal:
    def test_dirty_tree_detected(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_dirty_tree_refusal
        _scenario_dirty_tree_refusal(tmp_path)


class TestScenarioRollbackAfterCommitWarn:
    def test_checkpoint_found(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_rollback_after_commit_warn
        _scenario_rollback_after_commit_warn(tmp_path)


class TestScenarioResumeAfterSigint:
    def test_interrupted_task_found(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_resume_after_sigint
        _scenario_resume_after_sigint(tmp_path)


class TestScenarioPinnedFilesInContext:
    def test_pinned_file_in_results(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_pinned_files_in_context
        _scenario_pinned_files_in_context(tmp_path)


class TestScenarioDebugBundleRedaction:
    def test_bundle_created(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_debug_bundle_redaction
        _scenario_debug_bundle_redaction(tmp_path)


class TestScenarioFailingTestRepair:
    def test_fix_flow_produces_patch(self, tmp_path: Path):
        from safecode.cli_smoke import _scenario_failing_test_repair
        _scenario_failing_test_repair(tmp_path)
