"""Tests for the v7.1.5 eval report dashboard."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.eval.dashboard import (
    build_eval_dashboard_sources,
    render_eval_dashboard,
    summarize_eval_json,
    write_eval_dashboard,
)


class TestEvalDashboardSummary:
    def test_missing_report_is_marked_missing(self, tmp_path: Path) -> None:
        source = summarize_eval_json("live", tmp_path / "missing.json")

        assert source.present is False
        assert source.total == 0
        assert source.passed == 0

    def test_summarizes_live_success_field(self, tmp_path: Path) -> None:
        path = tmp_path / "live.json"
        path.write_text(json.dumps({
            "results": [
                {"fixture_name": "ok", "success": True},
                {"fixture_name": "bad", "success": False, "error": "failed"},
            ]
        }), encoding="utf-8")

        source = summarize_eval_json("live", path)

        assert source.present is True
        assert source.total == 2
        assert source.passed == 1
        assert source.failures == ["bad: failed"]

    def test_summarizes_swebench_passed_field(self, tmp_path: Path) -> None:
        path = tmp_path / "swe.json"
        path.write_text(json.dumps({
            "results": [
                {"instance_id": "task-a", "passed": True},
                {"instance_id": "task-b", "passed": False, "failure_reasons": ["patch_parse"]},
            ]
        }), encoding="utf-8")

        source = summarize_eval_json("swebench-lite", path)

        assert source.total == 2
        assert source.passed == 1
        assert source.failures == ["task-b: patch_parse"]


class TestEvalDashboardRender:
    def test_render_dashboard_contains_overall_and_failures(self, tmp_path: Path) -> None:
        source = summarize_eval_json("live", tmp_path / "missing.json")
        text = render_eval_dashboard([source])

        assert "# SafeCode Eval Dashboard" in text
        assert "Overall: 0/0 passed" in text
        assert "| live | missing | 0/0 | 0.0%" in text

    def test_build_default_sources_reads_project_paths(self, tmp_path: Path) -> None:
        live_dir = tmp_path / "tests" / "snapshots" / "live_eval"
        live_dir.mkdir(parents=True)
        (live_dir / "latest.json").write_text(
            json.dumps({"results": [{"fixture_name": "ok", "success": True}]}),
            encoding="utf-8",
        )

        sources = build_eval_dashboard_sources(tmp_path)

        by_name = {source.name: source for source in sources}
        assert by_name["live"].present is True
        assert by_name["live"].passed == 1
        assert by_name["swebench-lite"].present is False

    def test_write_eval_dashboard(self, tmp_path: Path) -> None:
        output = tmp_path / ".sac" / "eval" / "dashboard.md"

        written = write_eval_dashboard(tmp_path, output)

        assert written == output
        assert "# SafeCode Eval Dashboard" in output.read_text(encoding="utf-8")


class TestEvalDashboardCLI:
    def test_eval_help_mentions_dashboard_mode(self) -> None:
        from typer.testing import CliRunner
        from safecode.cli_ops import ops_app

        result = CliRunner().invoke(ops_app, ["eval", "--help"])

        assert result.exit_code == 0
        assert "dashboard" in result.output
