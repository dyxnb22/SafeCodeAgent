"""Tests for the v7.1.4 real-task benchmark lane."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.eval.real_task import (
    build_real_task_manifest,
    is_real_task,
    load_default_real_tasks,
    render_real_task_report,
    save_real_task_report,
)
from safecode.eval.swebench_adapter import SWEBenchReport, SWEBenchTask, SWEBenchTaskResult


def _task(instance_id: str) -> SWEBenchTask:
    return SWEBenchTask(
        instance_id=instance_id,
        problem_statement="Fix it.",
        repo={"kind": "inline", "files": {"x.py": "x = 1\n"}, "setup_commands": []},
        test_command="python -m pytest -q",
        pass_condition="exit_code_0",
    )


class TestRealTaskSelection:
    def test_safecode_micro_fixture_is_not_real_task(self) -> None:
        assert is_real_task(_task("safecode__calc-zero-div")) is False

    def test_external_issue_fixture_is_real_task(self) -> None:
        assert is_real_task(_task("arrow__parser-error-boundary")) is True

    def test_builtin_real_task_slice_contains_arrow_fixture(self) -> None:
        tasks = load_default_real_tasks()
        assert [task.instance_id for task in tasks] == ["arrow__parser-error-boundary"]

    def test_manifest_records_selection_rule(self) -> None:
        manifest = build_real_task_manifest([_task("arrow__parser-error-boundary")])
        data = manifest.to_dict()
        assert data["suite"] == "real-task"
        assert data["source_suite"] == "swebench-lite"
        assert data["total"] == 1
        assert data["task_ids"] == ["arrow__parser-error-boundary"]
        assert "safecode__" in data["selection_rule"]


class TestRealTaskReport:
    def _report(self) -> SWEBenchReport:
        return SWEBenchReport(
            suite="real-task",
            run_at="2026-06-17T00:00:00+00:00",
            provider="mock",
            total=1,
            passed=1,
            results=[
                SWEBenchTaskResult(
                    instance_id="arrow__parser-error-boundary",
                    passed=True,
                    exit_code=0,
                    output_snippet="",
                    failure_reasons=[],
                    wall_seconds=0.1,
                    stopped_reason="passed",
                )
            ],
        )

    def test_save_real_task_report(self, tmp_path: Path) -> None:
        path = save_real_task_report(self._report(), out_dir=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert path.name == "latest.json"
        assert data["suite"] == "real-task"
        assert data["passed"] == 1

    def test_render_real_task_report_mentions_source_and_task(self) -> None:
        manifest = build_real_task_manifest([_task("arrow__parser-error-boundary")])
        text = render_real_task_report(self._report(), manifest)
        assert "Real-task Benchmark" in text
        assert "swebench-lite" in text
        assert "arrow__parser-error-boundary" in text


class TestRealTaskCLI:
    def test_eval_help_mentions_real_task_mode(self) -> None:
        from typer.testing import CliRunner
        from safecode.cli_ops import ops_app

        result = CliRunner().invoke(ops_app, ["eval", "--help"])

        assert result.exit_code == 0
        assert "real-task" in result.output
