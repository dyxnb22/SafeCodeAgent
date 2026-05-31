"""Agent task journal tests for v2.0.2."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.agent.session import AgentSessionStore
from safecode.cli import app
from safecode.report.render import ReportRenderer
from safecode.state.journal import AgentJournalEvent, AgentJournalStore

runner = CliRunner()


def test_session_start_records_plan_journal(tmp_path):
    state = AgentSessionStore(tmp_path).start("ship journal", plan=["inspect", "summarize"])

    events = AgentJournalStore(tmp_path).read(state.session_id)

    assert [event.type for event in events] == ["plan"]
    assert events[0].payload["goal"] == "ship journal"
    assert events[0].payload["steps"] == ["inspect", "summarize"]


def test_agent_loop_records_action_and_final_summary(tmp_path):
    result = AgentLoop(tmp_path).run("finish journal", max_steps=5)

    events = AgentJournalStore(tmp_path).read(result.state.session_id)
    event_types = [event.type for event in events]

    assert event_types[0] == "plan"
    assert event_types.count("action") == 3
    assert event_types[-1] == "final_summary"
    assert events[-1].payload["summary"]["status"] == "completed"


def test_abort_records_failure_journal_event(tmp_path):
    store = AgentSessionStore(tmp_path)
    state = store.start("recover journal")

    store.abort("manual stop")

    events = AgentJournalStore(tmp_path).read(state.session_id)
    assert events[-1].type == "failure"
    assert events[-1].payload["details"]["reason"] == "manual stop"


def test_journal_cli_renders_current_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["agent", "run", "ship", "--max-steps", "1"])

    result = runner.invoke(app, ["agent", "journal"])

    assert result.exit_code == 0
    assert "SafeCode Agent Journal" in result.stdout
    assert "plan" in result.stdout
    assert "action" in result.stdout


def test_journal_store_replaces_symlink_without_following(tmp_path):
    store = AgentJournalStore(tmp_path)
    session_id = "session_safe_123"
    path = store.path_for(session_id)
    path.parent.mkdir(parents=True)
    outside = tmp_path.parent / f"outside-journal-{tmp_path.name}.jsonl"
    outside.write_text("outside must not change", encoding="utf-8")
    path.symlink_to(outside)

    store.append(AgentJournalEvent(session_id=session_id, type="action", message="safe append"))

    assert outside.read_text(encoding="utf-8") == "outside must not change"
    assert path.exists()
    assert not path.is_symlink()
    assert store.read(session_id)[0].message == "safe append"


def test_journal_store_rejects_path_like_session_id(tmp_path):
    store = AgentJournalStore(tmp_path)

    with pytest.raises(ValueError, match="Invalid agent session id"):
        store.read("../escape")


def test_report_renderer_includes_latest_journal_summary(tmp_path):
    result = AgentLoop(tmp_path).run("report journal", max_steps=5)

    report = ReportRenderer(tmp_path).render_markdown()

    assert "## Latest Agent Journal" in report
    assert result.state.session_id in report
    assert "Plan already completed." in report


def test_journal_file_is_jsonl(tmp_path):
    result = AgentLoop(tmp_path).step("jsonl journal")
    path = AgentJournalStore(tmp_path).path_for(result.state.session_id)

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert [json.loads(line)["type"] for line in lines] == ["plan", "action"]
