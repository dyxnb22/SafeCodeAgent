from typer.testing import CliRunner

from safecode.agent.session import AgentSessionStore
from safecode.cli import app
from safecode.state.journal import AgentJournalStore
from safecode.tui.dashboard import render_dashboard


def test_dashboard_renders_empty_project(tmp_path):
    output = render_dashboard(tmp_path)
    assert "SafeCode TUI" in output
    assert "No active session" in output
    assert "Pending Diff" in output
    assert "History" in output


def test_dashboard_renders_session_plan_and_history(tmp_path):
    state = AgentSessionStore(tmp_path).start("Fix a bug", plan=["Inspect", "Patch"])
    AgentJournalStore(tmp_path).record_plan(state.session_id, state.goal, state.plan)

    output = render_dashboard(tmp_path)

    assert "Fix a bug" in output
    assert "Inspect" in output
    assert "planned" in output.lower()


def test_tui_dashboard_cli_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["tui", "dashboard"])
    assert result.exit_code == 0
    assert "SafeCode TUI" in result.output
