from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.cli import app
from safecode.project.formatter import detect_formatters
from safecode.shell_session.state import ShellTurn
from safecode.shell_session.store import ShellSessionStore


runner = CliRunner()


def _json(output: str) -> dict:
    return json.loads(output)


def test_agent_loop_plan_mode_registers_readonly_tools_only(tmp_path: Path) -> None:
    loop = AgentLoop(tmp_path, plan_mode=True)
    names = {spec.name for spec in loop._build_dispatcher().specs()}
    assert {"read_file", "list_files", "search_files", "grep_files"}.issubset(names)
    assert "edit_file" not in names
    assert "write_file" not in names
    assert "run_command" not in names


def test_shell_mode_plan_json_reports_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["shell", "--agentic", "--mode", "plan", "--json", "--non-tty"],
        input="/mode\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    payload = _json(result.stdout)
    assert payload["status"] == "success"
    assert payload["data"]["mode"] == "plan"


def test_lsp_status_json_fail_soft(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["lsp", "status", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = _json(result.stdout)
    assert payload["status"] == "success"
    assert {item["language"] for item in payload["data"]["services"]} >= {"python", "typescript", "go", "rust"}


def test_session_list_stats_export_import_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = ShellSessionStore(tmp_path)
    state = store.create(task_id="task-1")
    state = state.model_copy(update={
        "turns": [
            ShellTurn(turn_index=0, user_input="token sk-test-secret", shell_response="ok")
        ]
    })
    store.save(state)

    result = runner.invoke(app, ["session", "list", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    assert _json(result.stdout)["data"]["sessions"][0]["session_id"] == state.session_id

    stats = runner.invoke(app, ["session", "stats", "--json"], catch_exceptions=False)
    assert stats.exit_code == 0
    assert _json(stats.stdout)["data"]["turns"] == 1

    export_path = tmp_path / "session.json"
    exported = runner.invoke(
        app,
        ["session", "export", state.session_id, "--output", str(export_path), "--json"],
        catch_exceptions=False,
    )
    assert exported.exit_code == 0
    assert export_path.exists()
    assert "sk-test-secret" not in export_path.read_text(encoding="utf-8")

    imported = runner.invoke(app, ["session", "import", str(export_path), "--json"], catch_exceptions=False)
    assert imported.exit_code == 0
    assert _json(imported.stdout)["data"]["session_id"] == state.session_id


def test_format_run_json_skips_when_no_formatter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["format", "run", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = _json(result.stdout)
    assert payload["data"]["status"] == "skipped"


def test_configured_formatter_detection(tmp_path: Path) -> None:
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text(
        '[formatter]\nenabled = false\ncommands = ["python -m ruff format ."]\n',
        encoding="utf-8",
    )
    detected = detect_formatters(tmp_path)
    assert detected[0].name == "configured-1"
    assert detected[0].command == ("python", "-m", "ruff", "format", ".")


def test_tools_list_includes_user_tools_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "tools.toml").write_text(
        '[[tools]]\n'
        'name = "project.schema"\n'
        'description = "Dump project schema"\n'
        'command = "python scripts/schema.py"\n'
        'risk = "low"\n'
        'permission = "read"\n'
        'approval = false\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["tools", "list", "--include-user", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = _json(result.stdout)
    assert payload["data"]["user_tools"][0]["name"] == "project.schema"
    assert payload["data"]["user_tools"][0]["source"] == "user"


def test_help_all_mentions_new_terminal_surfaces() -> None:
    result = runner.invoke(app, ["help", "--all"], catch_exceptions=False)
    assert result.exit_code == 0
    for name in ("lsp", "session", "format", "test-gen", "refactor"):
        assert name in result.stdout
