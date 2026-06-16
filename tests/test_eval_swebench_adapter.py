"""Tests for the SWE-bench Lite eval harness (v6.5.0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.eval.swebench_adapter import (
    SWEBENCH_SCHEMA_VERSION,
    SWEBenchLoadError,
    SWEBenchReport,
    SWEBenchRunner,
    SWEBenchTask,
    SWEBenchTaskResult,
    load_task_from_dict,
    load_tasks_from_dir,
    render_report_text,
    save_report,
    task_to_fixture,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_TASK = {
    "schema_version": 1,
    "instance_id": "proj__issue-1",
    "problem_statement": "Fix the bug in foo.py.",
    "repo": {
        "kind": "inline",
        "files": {"foo.py": "def foo(): pass\n" * 5},
        "setup_commands": [],
    },
    "test_command": "python -m pytest tests/ -q",
    "pass_condition": "exit_code_0",
    "hints": "",
}


def _make_task(**overrides) -> dict:
    d = dict(_MINIMAL_TASK)
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# load_task_from_dict
# ---------------------------------------------------------------------------


class TestLoadTaskFromDict:
    def test_valid_task_loads(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        assert task.instance_id == "proj__issue-1"
        assert task.problem_statement == "Fix the bug in foo.py."
        assert task.test_command == "python -m pytest tests/ -q"
        assert task.pass_condition == "exit_code_0"

    def test_schema_version_1(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        assert task.schema_version == SWEBENCH_SCHEMA_VERSION

    def test_unsupported_schema_version_raises(self) -> None:
        with pytest.raises(SWEBenchLoadError, match="schema_version"):
            load_task_from_dict(_make_task(schema_version=99))

    def test_missing_instance_id_raises(self) -> None:
        d = dict(_MINIMAL_TASK)
        del d["instance_id"]
        with pytest.raises(SWEBenchLoadError, match="instance_id"):
            load_task_from_dict(d)

    def test_missing_problem_statement_raises(self) -> None:
        d = dict(_MINIMAL_TASK)
        del d["problem_statement"]
        with pytest.raises(SWEBenchLoadError, match="problem_statement"):
            load_task_from_dict(d)

    def test_missing_repo_raises(self) -> None:
        d = dict(_MINIMAL_TASK)
        del d["repo"]
        with pytest.raises(SWEBenchLoadError, match="repo"):
            load_task_from_dict(d)

    def test_missing_test_command_raises(self) -> None:
        d = dict(_MINIMAL_TASK)
        del d["test_command"]
        with pytest.raises(SWEBenchLoadError, match="test_command"):
            load_task_from_dict(d)

    def test_missing_pass_condition_raises(self) -> None:
        d = dict(_MINIMAL_TASK)
        del d["pass_condition"]
        with pytest.raises(SWEBenchLoadError, match="pass_condition"):
            load_task_from_dict(d)

    def test_non_dict_raises(self) -> None:
        with pytest.raises(SWEBenchLoadError):
            load_task_from_dict([])  # type: ignore[arg-type]

    def test_hints_optional(self) -> None:
        d = dict(_MINIMAL_TASK)
        del d["hints"]
        task = load_task_from_dict(d)
        assert task.hints == ""


# ---------------------------------------------------------------------------
# load_tasks_from_dir
# ---------------------------------------------------------------------------


class TestLoadTasksFromDir:
    def _write_task(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_loads_valid_files(self, tmp_path: Path) -> None:
        self._write_task(tmp_path / "t1.json", _MINIMAL_TASK)
        self._write_task(tmp_path / "t2.json", _make_task(instance_id="proj__issue-2"))
        tasks = load_tasks_from_dir(tmp_path)
        assert len(tasks) == 2

    def test_skips_non_json_files(self, tmp_path: Path) -> None:
        self._write_task(tmp_path / "t1.json", _MINIMAL_TASK)
        (tmp_path / "readme.md").write_text("not a task")
        tasks = load_tasks_from_dir(tmp_path)
        assert len(tasks) == 1

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        tasks = load_tasks_from_dir(tmp_path)
        assert tasks == []

    def test_all_invalid_raises(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("{}")
        with pytest.raises(SWEBenchLoadError):
            load_tasks_from_dir(tmp_path)

    def test_sorted_by_filename(self, tmp_path: Path) -> None:
        self._write_task(tmp_path / "b.json", _make_task(instance_id="b"))
        self._write_task(tmp_path / "a.json", _make_task(instance_id="a"))
        tasks = load_tasks_from_dir(tmp_path)
        assert tasks[0].instance_id == "a"
        assert tasks[1].instance_id == "b"


# ---------------------------------------------------------------------------
# task_to_fixture
# ---------------------------------------------------------------------------


class TestTaskToFixture:
    def test_instance_id_becomes_fixture_name(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        fixture = task_to_fixture(task)
        assert fixture.name == task.instance_id

    def test_problem_statement_becomes_goal(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        fixture = task_to_fixture(task)
        assert task.problem_statement in fixture.goal

    def test_hints_appended_to_goal(self) -> None:
        task = load_task_from_dict(_make_task(hints="Use .get()"))
        fixture = task_to_fixture(task)
        assert "Use .get()" in fixture.goal

    def test_test_command_in_validation_commands(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        fixture = task_to_fixture(task)
        assert task.test_command in fixture.validation_commands

    def test_exit_code_0_pass_condition(self) -> None:
        task = load_task_from_dict(_make_task(pass_condition="exit_code_0"))
        fixture = task_to_fixture(task)
        assert fixture.expected.expected_exit_code == 0

    def test_output_contains_pass_condition(self) -> None:
        task = load_task_from_dict(_make_task(pass_condition="output_contains:PASSED"))
        fixture = task_to_fixture(task)
        assert "PASSED" in fixture.expected.expected_output_contains

    def test_swebench_lite_tag(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        fixture = task_to_fixture(task)
        assert "swebench-lite" in fixture.tags

    def test_safety_defaults_are_conservative(self) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        fixture = task_to_fixture(task)
        assert fixture.safety.expect_diff_review is True
        assert fixture.safety.expect_checkpoint is True
        assert fixture.safety.allow_network is False


# ---------------------------------------------------------------------------
# SWEBenchTaskResult / SWEBenchReport
# ---------------------------------------------------------------------------


class TestResultAndReport:
    def test_result_to_dict(self) -> None:
        r = SWEBenchTaskResult(
            instance_id="proj__issue-1",
            passed=True,
            exit_code=0,
            output_snippet="ok",
            failure_reasons=[],
            wall_seconds=1.5,
            stopped_reason="passed",
        )
        d = r.to_dict()
        assert d["instance_id"] == "proj__issue-1"
        assert d["passed"] is True
        assert d["exit_code"] == 0

    def test_report_to_dict(self) -> None:
        r = SWEBenchTaskResult(
            instance_id="x", passed=False, exit_code=1,
            output_snippet="", failure_reasons=["patch_parse"],
            wall_seconds=0.5, stopped_reason="failed",
        )
        report = SWEBenchReport(
            suite="swebench-lite",
            run_at="2026-06-16T00:00:00+00:00",
            provider="mock",
            total=1,
            passed=0,
            results=[r],
        )
        d = report.to_dict()
        assert d["total"] == 1
        assert d["passed"] == 0
        assert d["pass_rate"] == 0.0
        assert len(d["results"]) == 1

    def test_pass_rate_calculation(self) -> None:
        report = SWEBenchReport(
            suite="swebench-lite", run_at="", provider="mock",
            total=4, passed=3,
        )
        assert abs(report.pass_rate - 0.75) < 1e-6

    def test_pass_rate_zero_total(self) -> None:
        report = SWEBenchReport(
            suite="swebench-lite", run_at="", provider="mock",
            total=0, passed=0,
        )
        assert report.pass_rate == 0.0


# ---------------------------------------------------------------------------
# render_report_text
# ---------------------------------------------------------------------------


class TestRenderReportText:
    def _make_report(self, passed: int = 1, total: int = 2) -> SWEBenchReport:
        results = []
        for i in range(total):
            ok = i < passed
            results.append(SWEBenchTaskResult(
                instance_id=f"task-{i}", passed=ok, exit_code=0 if ok else 1,
                output_snippet="", failure_reasons=[] if ok else ["patch_parse"],
                wall_seconds=1.0, stopped_reason="passed" if ok else "failed",
            ))
        return SWEBenchReport(
            suite="swebench-lite", run_at="2026-06-16T00:00:00+00:00",
            provider="mock", total=total, passed=passed, results=results,
        )

    def test_report_contains_pass_count(self) -> None:
        text = render_report_text(self._make_report(1, 2))
        assert "1/2" in text

    def test_report_contains_suite(self) -> None:
        text = render_report_text(self._make_report())
        assert "swebench-lite" in text

    def test_report_contains_pass_fail_markers(self) -> None:
        text = render_report_text(self._make_report(1, 2))
        assert "PASS" in text
        assert "FAIL" in text

    def test_report_contains_instance_ids(self) -> None:
        text = render_report_text(self._make_report(1, 2))
        assert "task-0" in text
        assert "task-1" in text


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------


class TestSaveReport:
    def test_saves_json_file(self, tmp_path: Path) -> None:
        report = SWEBenchReport(
            suite="swebench-lite", run_at="2026-06-16T00:00:00+00:00",
            provider="mock", total=1, passed=0,
        )
        out = save_report(report, out_dir=tmp_path)
        assert out.exists()
        assert out.name == "latest.json"

    def test_saved_json_is_valid(self, tmp_path: Path) -> None:
        report = SWEBenchReport(
            suite="swebench-lite", run_at="2026-06-16T00:00:00+00:00",
            provider="mock", total=2, passed=1,
            results=[
                SWEBenchTaskResult("t1", True, 0, "", [], 1.0, "passed"),
                SWEBenchTaskResult("t2", False, 1, "", ["err"], 0.5, "failed"),
            ],
        )
        out = save_report(report, out_dir=tmp_path)
        data = json.loads(out.read_text())
        assert data["total"] == 2
        assert data["passed"] == 1
        assert len(data["results"]) == 2

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        report = SWEBenchReport("swebench-lite", "", "mock", 0, 0)
        nested = tmp_path / "deep" / "dir"
        out = save_report(report, out_dir=nested)
        assert out.exists()


# ---------------------------------------------------------------------------
# SWEBenchRunner (integration — mock provider)
# ---------------------------------------------------------------------------


class TestSWEBenchRunner:
    def test_runner_runs_task(self, tmp_path: Path) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        runner = SWEBenchRunner(project_root=tmp_path)
        result = runner.run(task)
        assert isinstance(result, SWEBenchTaskResult)
        assert result.instance_id == "proj__issue-1"
        assert isinstance(result.passed, bool)
        assert result.wall_seconds >= 0

    def test_runner_run_suite(self, tmp_path: Path) -> None:
        tasks = [
            load_task_from_dict(_MINIMAL_TASK),
            load_task_from_dict(_make_task(instance_id="proj__issue-2")),
        ]
        runner = SWEBenchRunner(project_root=tmp_path)
        report = runner.run_suite(tasks, provider="mock")
        assert report.total == 2
        assert report.suite == "swebench-lite"
        assert report.provider == "mock"

    def test_runner_respects_limit(self, tmp_path: Path) -> None:
        tasks = [load_task_from_dict(_make_task(instance_id=f"proj__issue-{i}")) for i in range(5)]
        runner = SWEBenchRunner(project_root=tmp_path)
        report = runner.run_suite(tasks, limit=2, provider="mock")
        assert report.total == 2

    def test_runner_report_has_results(self, tmp_path: Path) -> None:
        task = load_task_from_dict(_MINIMAL_TASK)
        runner = SWEBenchRunner(project_root=tmp_path)
        report = runner.run_suite([task], provider="mock")
        assert len(report.results) == 1

    def test_runner_never_raises(self, tmp_path: Path) -> None:
        """Runner must catch internal errors and record them as failures."""
        broken = _make_task(repo={"kind": "local", "path": "/nonexistent/path/here"})
        task = load_task_from_dict(broken)
        runner = SWEBenchRunner(project_root=tmp_path)
        result = runner.run(task)
        assert isinstance(result, SWEBenchTaskResult)


# ---------------------------------------------------------------------------
# Built-in fixture files
# ---------------------------------------------------------------------------


class TestBuiltinFixtures:
    _FIXTURE_DIR = (
        Path(__file__).parent / "eval_fixtures" / "swebench_lite"
    )

    def test_fixture_dir_exists(self) -> None:
        assert self._FIXTURE_DIR.is_dir()

    def test_fixture_files_are_valid(self) -> None:
        tasks = load_tasks_from_dir(self._FIXTURE_DIR)
        assert len(tasks) >= 2

    def test_all_fixtures_have_inline_repos(self) -> None:
        tasks = load_tasks_from_dir(self._FIXTURE_DIR)
        for task in tasks:
            assert task.repo.get("kind") == "inline"

    def test_all_fixtures_have_test_commands(self) -> None:
        tasks = load_tasks_from_dir(self._FIXTURE_DIR)
        for task in tasks:
            assert task.test_command


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


class TestSWEBenchCLI:
    def test_swebench_mode_missing_dir_exits_1(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from safecode.cli_ops import ops_app
        runner = CliRunner()
        result = runner.invoke(
            ops_app,
            ["eval", "--mode", "swebench-lite", "--suite", str(tmp_path / "nonexistent")],
            catch_exceptions=False,
        )
        assert result.exit_code == 1

    def test_swebench_mode_empty_dir_exits_0(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from safecode.cli_ops import ops_app
        runner = CliRunner()
        result = runner.invoke(
            ops_app,
            ["eval", "--mode", "swebench-lite", "--suite", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_swebench_mode_with_valid_suite(self, tmp_path: Path) -> None:
        # Write one valid task
        (tmp_path / "t1.json").write_text(json.dumps(_MINIMAL_TASK), encoding="utf-8")
        from typer.testing import CliRunner
        from safecode.cli_ops import ops_app
        runner = CliRunner()
        result = runner.invoke(
            ops_app,
            ["eval", "--mode", "swebench-lite", "--suite", str(tmp_path), "--limit", "1"],
            catch_exceptions=False,
        )
        # May pass or fail based on mock provider; just verify it runs
        assert result.exit_code in {0, 1}
        assert "swebench-lite" in result.output.lower() or "SWE" in result.output
