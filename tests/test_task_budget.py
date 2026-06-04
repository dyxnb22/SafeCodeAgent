"""Tests for per-task budgets (v4.4.1 T-4.4.1-A)."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.agent.schemas import AgentPlanResponse, AgentToolIntentResponse
from safecode.agent.tools import ToolIntent
from safecode.cli import app
from safecode.task.budget import TaskBudgetStore
from safecode.task.store import TaskStore

runner = CliRunner()


class _ReadLLM:
    def plan(self, goal, context):
        return AgentPlanResponse(goal=goal, steps=["one", "two", "three"])

    def choose_tool(self, goal, context):
        return AgentToolIntentResponse(
            intent=ToolIntent(type="read", target="README.md", description="read docs"),
            rationale="read",
        )


def _invoke(tmp_path, args):
    with patch("safecode.cli_task.Path") as mock_path:
        mock_path.cwd.return_value = tmp_path
        return runner.invoke(app, args)


class TestTaskBudgetCLI:
    def test_budget_defaults(self, tmp_path):
        state = TaskStore(tmp_path).create("budget defaults")

        budget = TaskBudgetStore(tmp_path).load(state.task_id)

        assert budget.steps == 8
        assert budget.time_seconds == 600
        assert budget.retries == 2
        assert budget.tokens == 60_000

    def test_budget_show_json(self, tmp_path):
        state = TaskStore(tmp_path).create("show budget")

        result = _invoke(tmp_path, ["task", "budget", "show", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "task budget show"
        assert data["data"]["task_id"] == state.task_id
        assert data["data"]["steps"] == 8
        assert data["data"]["experimental"] is True

    def test_budget_set_json(self, tmp_path):
        state = TaskStore(tmp_path).create("set budget")

        result = _invoke(
            tmp_path,
            [
                "task",
                "budget",
                "set",
                "--steps",
                "3",
                "--time-seconds",
                "44",
                "--retries",
                "5",
                "--tokens",
                "1234",
                "--json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["task_id"] == state.task_id
        assert data["steps"] == 3
        assert data["time_seconds"] == 44
        assert data["retries"] == 5
        assert data["tokens"] == 1234
        assert TaskBudgetStore(tmp_path).load(state.task_id).steps == 3

    def test_budget_set_explicit_task(self, tmp_path):
        store = TaskStore(tmp_path)
        first = store.create("first")
        store.create("second")

        result = _invoke(tmp_path, ["task", "budget", "set", "--task", first.task_id, "--steps", "2", "--json"])

        assert result.exit_code == 0
        assert TaskBudgetStore(tmp_path).load(first.task_id).steps == 2

    def test_invalid_budget_values_are_rejected(self, tmp_path):
        TaskStore(tmp_path).create("invalid")

        result = _invoke(tmp_path, ["task", "budget", "set", "--steps", "0", "--json"])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "positive integers" in data["error"]

    def test_budget_command_requires_task(self, tmp_path):
        result = _invoke(tmp_path, ["task", "budget", "show", "--json"])

        assert result.exit_code == 1
        assert "CURRENT" in json.loads(result.output)["error"]


class TestTaskBudgetEnforcement:
    def test_step_budget_records_budget_exceeded(self, tmp_path):
        task = TaskStore(tmp_path).create("loop with budget")
        TaskBudgetStore(tmp_path).save(TaskBudgetStore(tmp_path).load(task.task_id).model_copy(update={"steps": 1}))

        result = AgentLoop(tmp_path, llm_client=_ReadLLM()).run("budgeted run", max_steps=3)

        assert result.stopped_reason == "budget_exceeded"
        assert result.state.last_error == "budget_exceeded: steps"
        loaded = TaskStore(tmp_path).load(task.task_id)
        assert loaded is not None
        assert loaded.iterations[-1].failure_category == "budget_exceeded"
        assert loaded.iterations[-1].mode == "steps"

    def test_budget_does_not_weaken_policy(self, tmp_path):
        from safecode.shell.runner import ShellRunner

        task = TaskStore(tmp_path).create("policy still wins")
        TaskBudgetStore(tmp_path).save(TaskBudgetStore(tmp_path).load(task.task_id).model_copy(update={"steps": 100}))

        result = ShellRunner(tmp_path).run("rm -rf /tmp/safecode-budget-test", approved=True)

        assert result.executed is False
        assert result.exit_code == 126
