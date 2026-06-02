"""Tests for v2.9.3 eval-loop-mode-ci-gate.

Verifies:
- CI workflow has a loop-eval job.
- loop-eval job has continue-on-error: true (advisory).
- loop-eval job installs dependencies and runs sac eval --mode loop.
- loop-eval job does not require live provider credentials or network calls.
- sac eval --mode loop exits 0 and shows all six fixture names.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from safecode.cli import app

CI_WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"

runner = CliRunner()


def _load_ci_workflow() -> dict:
    assert CI_WORKFLOW_PATH.exists(), f"CI workflow not found: {CI_WORKFLOW_PATH}"
    return yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))


# ── CI workflow structure ─────────────────────────────────────────────────


class TestCIWorkflowLoopEvalJob:
    def test_loop_eval_job_exists(self):
        workflow = _load_ci_workflow()
        assert "loop-eval" in workflow["jobs"], "loop-eval job missing from CI workflow"

    def test_loop_eval_job_has_continue_on_error(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        assert job.get("continue-on-error") is True, (
            "loop-eval job must have continue-on-error: true (advisory, not blocking)"
        )

    def test_loop_eval_job_has_name(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        assert "name" in job

    def test_loop_eval_job_runs_on_ubuntu(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        assert "ubuntu" in job.get("runs-on", "")

    def test_loop_eval_job_has_checkout_step(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        step_uses = [s.get("uses", "") for s in job["steps"]]
        assert any("actions/checkout" in u for u in step_uses)

    def test_loop_eval_job_installs_dependencies(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        run_cmds = [s.get("run", "") for s in job["steps"]]
        assert any("pip install" in r or "uv sync" in r for r in run_cmds), (
            "loop-eval job must install dependencies"
        )

    def test_loop_eval_job_runs_eval_loop_mode(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        run_cmds = " ".join(s.get("run", "") for s in job["steps"])
        assert "eval" in run_cmds and "loop" in run_cmds, (
            "loop-eval job must run sac eval --mode loop"
        )

    def test_loop_eval_job_does_not_set_openai_key(self):
        """No live provider credentials should appear in the job definition."""
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["loop-eval"]
        job_text = str(job)
        assert "OPENAI_API_KEY" not in job_text
        assert "ANTHROPIC_API_KEY" not in job_text

    def test_main_test_job_still_exists(self):
        workflow = _load_ci_workflow()
        assert "test" in workflow["jobs"], "Main 'test' job removed from CI workflow"

    def test_main_test_job_is_not_advisory(self):
        workflow = _load_ci_workflow()
        job = workflow["jobs"]["test"]
        assert not job.get("continue-on-error"), (
            "Main 'test' job must not have continue-on-error"
        )


# ── sac eval --mode loop behaves correctly ────────────────────────────────


class TestEvalLoopModeBehavior:
    EXPECTED_NAMES = {
        "docs-edit",
        "python-function-fix",
        "config-update-fix",
        "test-assertion-fix",
        "shell-readonly-check",
        "import-cleanup",
    }

    def test_eval_loop_mode_exits_zero(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "loop"], catch_exceptions=False)
        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

    def test_eval_loop_mode_shows_all_fixture_names(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "loop"], catch_exceptions=False)
        for name in self.EXPECTED_NAMES:
            assert name in result.output, f"Fixture {name!r} not shown in CLI output"

    def test_eval_loop_mode_no_network_markers(self, monkeypatch, tmp_path):
        """Output must not contain markers that indicate live provider calls."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "loop"], catch_exceptions=False)
        assert "openai" not in result.output.lower()
        assert "anthropic" not in result.output.lower()
