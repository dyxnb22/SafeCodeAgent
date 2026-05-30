"""Interactive agent session tests for v1.9.x."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.agent.session import AgentSessionStore
from safecode.cli import app

runner = CliRunner()


class TestAgentSessionStore:
    def test_start_writes_session_state(self, tmp_path):
        store = AgentSessionStore(tmp_path)
        state = store.start("fix the tests")

        loaded = store.load()
        assert loaded is not None
        assert loaded.session_id == state.session_id
        assert loaded.goal == "fix the tests"
        assert loaded.status == "active"
        assert loaded.current_step == 0
        assert store.path.exists()

    def test_load_invalid_session_returns_none(self, tmp_path):
        store = AgentSessionStore(tmp_path)
        store.path.parent.mkdir(parents=True)
        store.path.write_text("{not json", encoding="utf-8")

        assert store.load() is None

    def test_save_replaces_existing_symlink_without_following(self, tmp_path):
        store = AgentSessionStore(tmp_path)
        store.path.parent.mkdir(parents=True)
        outside = tmp_path.parent / f"outside-session-{tmp_path.name}.json"
        outside.write_text("outside must not change", encoding="utf-8")
        store.path.symlink_to(outside)

        store.start("safe goal")

        assert outside.read_text(encoding="utf-8") == "outside must not change"
        assert store.path.exists()
        assert not store.path.is_symlink()
        assert store.load() is not None


class TestAgentSessionCLI:
    def test_agent_status_without_session(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["agent", "status"])

        assert result.exit_code == 0
        assert "No agent session" in result.stdout

    def test_agent_start_status_clear_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        start = runner.invoke(app, ["agent", "start", "ship v1.9"])
        assert start.exit_code == 0
        assert "ship v1.9" in start.stdout

        data = json.loads((tmp_path / ".sac" / "session.json").read_text(encoding="utf-8"))
        assert data["goal"] == "ship v1.9"

        status = runner.invoke(app, ["agent", "status"])
        assert status.exit_code == 0
        assert "ship v1.9" in status.stdout

        clear = runner.invoke(app, ["agent", "clear"])
        assert clear.exit_code == 0
        assert not (tmp_path / ".sac" / "session.json").exists()


class TestAgentStep:
    def test_step_with_goal_creates_session_and_advances_once(self, tmp_path):
        result = AgentLoop(tmp_path).step("fix one bug")

        assert result.state.goal == "fix one bug"
        assert result.state.current_step == 1
        assert len(result.state.plan) == 3
        assert result.state.pending_action is not None
        assert result.state.pending_action["type"] == "read"

    def test_step_without_session_and_goal_fails_closed(self, tmp_path):
        try:
            AgentLoop(tmp_path).step()
        except FileNotFoundError as exc:
            assert "No agent session" in str(exc)
        else:
            raise AssertionError("step without session or goal should fail")

    def test_step_cli_advances_existing_session_once(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["agent", "start", "ship"])

        result = runner.invoke(app, ["agent", "step"])

        assert result.exit_code == 0
        data = json.loads((tmp_path / ".sac" / "session.json").read_text(encoding="utf-8"))
        assert data["current_step"] == 1
        assert data["pending_action"]["type"] == "read"
        assert data["pending_action"]["route"] == "context.read"
        assert data["pending_action"]["executable_now"] == "true"


class TestAgentRun:
    def test_run_advances_until_completed(self, tmp_path):
        result = AgentLoop(tmp_path).run("finish the plan", max_steps=5)

        assert result.stopped_reason == "completed"
        assert result.state.status == "completed"
        assert result.state.current_step == 3
        assert len(result.steps) == 4

    def test_run_respects_max_steps(self, tmp_path):
        result = AgentLoop(tmp_path).run("partial plan", max_steps=2)

        assert result.stopped_reason == "max_steps_reached"
        assert result.state.status == "active"
        assert result.state.current_step == 2
        assert len(result.steps) == 2

    def test_run_rejects_invalid_max_steps(self, tmp_path):
        try:
            AgentLoop(tmp_path).run("bad", max_steps=0)
        except ValueError as exc:
            assert "max_steps" in str(exc)
        else:
            raise AssertionError("max_steps=0 should fail")

    def test_run_cli_bounded_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["agent", "run", "ship", "--max-steps", "2"])

        assert result.exit_code == 0
        assert "max_steps_reached" in result.stdout
        data = json.loads((tmp_path / ".sac" / "session.json").read_text(encoding="utf-8"))
        assert data["current_step"] == 2
