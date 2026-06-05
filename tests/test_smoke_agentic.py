"""Tests for v4.11.5 deterministic agentic smoke scenarios."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_smoke import run_agentic_smoke


runner = CliRunner()


EXPECTED = {
    "plan-only": ["plan"],
    "edit-reject-approval": ["plan", "edit"],
    "apply-validation-pass-commit-prompt": ["plan", "edit", "apply", "run", "commit"],
    "validation-fail-repair-pass": ["plan", "edit", "apply", "run", "fix", "apply", "run"],
    "validation-fail-loop-no-progress": ["plan", "edit", "apply", "run", "fix"],
    "interrupted-resume-recover": ["plan", "edit", "apply", "apply"],
}


class TestAgenticSmokeRunner:
    def test_every_scenario_passes_and_reports_step_kinds(self) -> None:
        result = run_agentic_smoke()
        assert result.all_passed
        assert [s.name for s in result.scenarios] == list(EXPECTED)
        for scenario in result.scenarios:
            assert list(scenario.step_kinds) == EXPECTED[scenario.name]
            assert scenario.final_status

    def test_each_scenario_can_run_individually(self) -> None:
        for name, kinds in EXPECTED.items():
            result = run_agentic_smoke(only=[name])
            assert result.all_passed
            assert len(result.scenarios) == 1
            assert list(result.scenarios[0].step_kinds) == kinds

    def test_loop_no_progress_final_status(self) -> None:
        result = run_agentic_smoke(only=["validation-fail-loop-no-progress"])
        scenario = result.scenarios[0]
        assert scenario.final_status == "loop_no_progress"
        assert scenario.failure_reason == "loop_no_progress"

    def test_no_provider_or_network_calls(self) -> None:
        with patch("safecode.cli_smoke.create_llm_client") as mock_create:
            result = run_agentic_smoke()
        assert result.all_passed
        assert not mock_create.called


class TestAgenticSmokeCLI:
    def test_json_envelope_shape(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["smoke", "agentic", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["command"] == "smoke agentic"
        assert payload["status"] == "pass"
        data = payload["data"]
        assert data["total"] == 6
        assert data["failed"] == 0
        assert data["all_passed"] is True
        first = data["scenarios"][0]
        assert {"name", "passed", "step_kinds", "final_status", "failure_reason"} <= set(first)

    def test_text_output_compact(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["smoke", "agentic", "--only", "plan-only"])
        assert result.exit_code == 0
        assert "plan-only" in result.output
        assert "scenarios passed" in result.output

    def test_command_help_lists_experimental_agentic(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["smoke", "--help"])
        assert result.exit_code == 0
        assert "agentic" in result.output

    def test_json_reports_failure_reason_for_loop_no_progress(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["smoke", "agentic", "--json", "--only", "validation-fail-loop-no-progress"])
        assert result.exit_code == 0
        scenario = json.loads(result.output)["data"]["scenarios"][0]
        assert scenario["final_status"] == "loop_no_progress"
        assert scenario["failure_reason"] == "loop_no_progress"
