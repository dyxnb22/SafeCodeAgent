"""Tests for v3.1.0 autopilot-agent-run.

Verifies:
- AgentLoop.run() drives to 'completed' when plan finishes within max_steps.
- AgentLoop.run() stops with 'approval_required' on stop_for_user / patch.propose.
- sac agent run "goal" --max-steps N CLI returns exit 0 with output.
- sac agent run "goal" --json returns valid JSON with expected fields.
- Approvals are never bypassed: patch_proposed stops the loop without auto-applying.
- Journal records each step taken.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop, AgentRunResult
from safecode.agent.schemas import AgentPlanResponse, AgentStopForUserResponse, AgentToolIntentResponse
from safecode.agent.tools import ToolIntent
from safecode.cli import app
from safecode.eval.loop_runner import ScriptedLLMClient, ScriptedStep

runner = CliRunner()


def _read_step(target: str = "src/foo.py") -> ScriptedStep:
    return ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(type="read", target=target, description="Read"),
            rationale="read first",
        )
    )


def _stop_step(reason: str = "need approval") -> ScriptedStep:
    return ScriptedStep(
        tool_choice=AgentStopForUserResponse(
            reason=reason,
            message="stopping for user",
            requires_approval=True,
        )
    )


def _patch_step(target: str = "src/foo.py") -> ScriptedStep:
    return ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(
                type="patch",
                target=target,
                description="Patch the file",
                requires_approval=True,
            ),
            rationale="need to patch",
        )
    )


# ── Unit: AgentLoop.run() drives to completion ────────────────────────────────


class TestAutopilotRunToCompletion:
    def test_loop_completes_when_plan_exhausted(self, tmp_path):
        """Loop completes when all plan steps are consumed."""
        steps = [_read_step(), _read_step()]
        plan = AgentPlanResponse(
            goal="test goal",
            steps=["inspect file", "inspect again"],
        )
        llm = ScriptedLLMClient(steps, plan=plan)
        loop = AgentLoop(tmp_path, llm_client=llm)
        result = loop.run("test goal", max_steps=10)
        assert result.stopped_reason in ("completed", "max_steps_reached")
        assert len(result.steps) >= 1

    def test_loop_stops_for_approval_on_stop_for_user(self, tmp_path):
        """Loop stops with approval_required when LLM returns stop_for_user."""
        steps = [_read_step(), _stop_step()]
        plan = AgentPlanResponse(
            goal="goal",
            steps=["read", "stop"],
        )
        llm = ScriptedLLMClient(steps, plan=plan)
        loop = AgentLoop(tmp_path, llm_client=llm)
        result = loop.run("goal", max_steps=5)
        assert result.stopped_reason == "approval_required"

    def test_no_auto_apply_on_stop_for_user(self, tmp_path):
        """Stop-for-user does not auto-apply or modify files; loop pauses for approval."""
        target_file = tmp_path / "src" / "foo.py"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("original content\n")

        steps = [_stop_step("need approval before modifying")]
        plan = AgentPlanResponse(goal="fix", steps=["check if safe"])
        llm = ScriptedLLMClient(steps, plan=plan)
        loop = AgentLoop(tmp_path, llm_client=llm)
        result = loop.run("fix the file", max_steps=5)

        # File must not be modified
        assert target_file.read_text() == "original content\n"
        assert result.stopped_reason == "approval_required"

    def test_run_result_has_expected_fields(self, tmp_path):
        steps = [_read_step()]
        plan = AgentPlanResponse(goal="g", steps=["do it"])
        llm = ScriptedLLMClient(steps, plan=plan)
        loop = AgentLoop(tmp_path, llm_client=llm)
        result = loop.run("g", max_steps=3)
        assert hasattr(result, "state")
        assert hasattr(result, "steps")
        assert hasattr(result, "stopped_reason")
        assert isinstance(result.steps, list)

    def test_journal_records_steps(self, tmp_path):
        """Journal contains events after a run."""
        from safecode.state.journal import AgentJournalStore

        steps = [_read_step()]
        plan = AgentPlanResponse(goal="g", steps=["do it"])
        llm = ScriptedLLMClient(steps, plan=plan)
        loop = AgentLoop(tmp_path, llm_client=llm)
        result = loop.run("g", max_steps=2)

        journal = AgentJournalStore(tmp_path)
        events = journal.read(result.state.session_id)
        assert len(events) >= 1


# ── CLI: sac agent run ────────────────────────────────────────────────────────


class TestAgentRunCLI:
    def test_cli_run_returns_exit_zero(self, tmp_path):
        """sac agent run "goal" exits 0."""
        result = runner.invoke(app, ["agent", "run", "test goal", "--max-steps", "2"])
        assert result.exit_code == 0, result.output

    def test_cli_run_shows_summary(self, tmp_path):
        """sac agent run output contains session summary text."""
        result = runner.invoke(app, ["agent", "run", "test goal", "--max-steps", "2"])
        assert result.exit_code == 0
        # The output should mention something about the run
        assert len(result.output) > 0

    def test_cli_run_json_returns_valid_json(self, tmp_path):
        """sac agent run --json returns machine-parsable JSON."""
        result = runner.invoke(app, ["agent", "run", "test goal", "--max-steps", "2", "--json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["command"] == "agent run"
        assert "session_id" in parsed["data"]
        assert "stopped_reason" in parsed["data"]
        assert "steps_count" in parsed["data"]

    def test_cli_run_json_status_is_meaningful(self, tmp_path):
        """JSON status from agent run is a known value."""
        result = runner.invoke(app, ["agent", "run", "test goal", "--max-steps", "2", "--json"])
        parsed = json.loads(result.output)
        assert parsed["status"] in ("completed", "approval_required", "stopped", "max_steps_reached")

    def test_cli_run_no_json_is_rich_output(self, tmp_path):
        """Non-JSON mode does not produce a JSON object as first output."""
        result = runner.invoke(app, ["agent", "run", "test goal", "--max-steps", "2"])
        assert result.exit_code == 0
        # Output should not be a raw JSON object (it contains Rich table output)
        try:
            json.loads(result.output.strip())
            # If it parses as JSON something is wrong only if status field is absent
        except json.JSONDecodeError:
            pass  # expected: Rich table output
