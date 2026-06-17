"""Tests for v7.0.3 productized read-only subagent roles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli import app
from safecode.subagents.roles import ROLE_PRESETS, get_role
from safecode.subagents.runner import SubagentRunResult
from safecode.subagents.task import SubagentTask


runner = CliRunner()


def test_role_presets_are_discoverable_and_readonly() -> None:
    assert set(ROLE_PRESETS) == {"explore", "review", "scout"}
    for name in ("explore", "review", "scout"):
        role = get_role(name)
        assert role.readonly is True
        assert "read_file" in role.allowed_tools
        assert "write_file" not in role.allowed_tools


def test_subagent_roles_command_lists_builtin_roles(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["subagent", "roles"])
    assert result.exit_code == 0
    assert "explore" in result.output
    assert "review" in result.output
    assert "scout" in result.output


def test_explore_role_runs_readonly_runner_and_journals(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result_path = tmp_path / ".sac" / "subagents" / "abc123" / "result.md"
    result_path.parent.mkdir(parents=True)
    result_path.write_text("Project files: src/a.py, tests/test_a.py\n", encoding="utf-8")

    captured: dict[str, str] = {}

    class FakeRunner:
        def __init__(self, project_root: Path):
            self.project_root = project_root

        def run(self, title: str, instructions: str) -> SubagentRunResult:
            captured["title"] = title
            captured["instructions"] = instructions
            task = SubagentTask(
                id="abc123",
                title=title,
                instructions=instructions,
                readonly=True,
                status="completed",
                result_path=str(result_path),
            )
            return SubagentRunResult(task=task, result_path=result_path, executed=True, error=None)

    with patch("safecode.cli_subagent.ReadonlySubagentRunner", FakeRunner):
        result = runner.invoke(app, ["subagent", "explore", "parser config handling"])

    assert result.exit_code == 0
    assert captured["title"].startswith("Explore:")
    assert "Read-only exploration" in captured["instructions"]

    journal = tmp_path / ".sac" / "agent_journals" / "subagent_roles.jsonl"
    text = journal.read_text(encoding="utf-8")
    assert "subagent_dispatch" in text
    assert "role=explore" in text
    assert "src/a.py" in text


def test_review_pending_role_accepts_no_positional_query(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeRunner:
        def __init__(self, project_root: Path):
            pass

        def run(self, title: str, instructions: str) -> SubagentRunResult:
            task = SubagentTask(
                id="def456",
                title=title,
                instructions=instructions,
                readonly=True,
                status="completed",
            )
            return SubagentRunResult(task=task, result_path=None, executed=True, error=None)

    with patch("safecode.cli_subagent.ReadonlySubagentRunner", FakeRunner):
        result = runner.invoke(app, ["subagent", "review", "--pending"])

    assert result.exit_code == 0
    assert "Role: review" in result.output


def test_review_without_target_or_pending_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["subagent", "review"])
    assert result.exit_code == 1
    assert "Provide a review target" in result.output
