"""Tests for v4.11.4 agentic resume support."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.agent.session import AgentSessionStore
from safecode.agent.step_model import TypedAgentStepResult
from safecode.cli import app
from safecode.state.journal import AgentJournalStore
from safecode.task.store import TaskStore


runner = CliRunner()


def _invoke(tmp_path: Path, args: list[str]):
    with patch("safecode.cli_resume.Path") as mock_path:
        mock_path.cwd.return_value = tmp_path
        return runner.invoke(app, args)


def _task_with_session(tmp_path: Path, session_id: str):
    store = TaskStore(tmp_path)
    state = store.create("agentic goal")
    updated = state.model_copy(update={"session_id": session_id})
    store.save(updated)
    return updated


def _journal(tmp_path: Path, session_id: str, *, status: str = "waiting_for_user") -> None:
    journal = AgentJournalStore(tmp_path)
    journal.record_plan(session_id, "agentic goal", ["plan", "edit", "apply"])
    journal.record_typed_result(
        session_id,
        TypedAgentStepResult(step_index=0, kind="edit", status=status, summary="pending edit"),
    )


class TestAgenticResume:
    def test_interrupted_after_plan_resumes_at_step_0_or_next_safe_step(self, tmp_path: Path) -> None:
        state = AgentSessionStore(tmp_path).start("agentic goal", plan=["first"])
        AgentJournalStore(tmp_path).record_typed_result(
            state.session_id,
            TypedAgentStepResult(step_index=0, kind="ask", status="interrupted", summary="interrupted"),
        )
        resumed = AgentLoop(tmp_path).resume_from(state.session_id)
        assert resumed.current_step == 0
        assert resumed.status == "waiting_for_user"

    def test_interrupted_mid_apply_re_presents_pending_patch_for_review(self, tmp_path: Path) -> None:
        session_id = "session-agentic-001"
        _task_with_session(tmp_path, session_id)
        _journal(tmp_path, session_id)
        (tmp_path / ".sac").mkdir(exist_ok=True)
        (tmp_path / ".sac" / "pending_patch.json").write_text("{}", encoding="utf-8")

        result = _invoke(tmp_path, ["resume", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)["data"]
        assert data["agentic_session"]["suggested_next_safe_step"] == "apply pending patch"

    def test_corrupted_journal_degrades_to_passive_v44_summary(self, tmp_path: Path) -> None:
        session_id = "session-agentic-002"
        task = _task_with_session(tmp_path, session_id)
        path = AgentJournalStore(tmp_path).path_for(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json}\n", encoding="utf-8")

        result = _invoke(tmp_path, ["resume", task.task_id, "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert "agentic_session" not in data
        assert data["task_id"] == task.task_id

    def test_continue_agent_invokes_agent_loop_run_without_bypassing_approval(self, tmp_path: Path) -> None:
        session_id = "session-agentic-003"
        _task_with_session(tmp_path, session_id)
        _journal(tmp_path, session_id)
        calls: dict[str, object] = {}

        class FakeLoop:
            def __init__(self, project_root):
                calls["project_root"] = project_root

            def resume_from(self, sid):
                calls["session_id"] = sid

            def run(self, goal):
                calls["goal"] = goal
                from safecode.agent.loop import AgentRunResult
                from safecode.agent.session import AgentSessionState
                from safecode.utils.time import utc_now_iso
                state = AgentSessionState(
                    session_id=session_id,
                    goal="agentic goal",
                    plan=["edit"],
                    current_step=0,
                    pending_action={"type": "patch"},
                    status="waiting_for_user",
                    last_observation="approval required",
                    last_error=None,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                return AgentRunResult(state=state, steps=[], stopped_reason="approval_required")

        with patch("safecode.cli_resume.AgentLoop", FakeLoop):
            result = _invoke(tmp_path, ["resume", "--continue-agent", "--json"])

        assert result.exit_code == 0, result.output
        assert calls["session_id"] == session_id
        assert calls["goal"] is None
        data = json.loads(result.output)["data"]
        assert data["continue_agent"]["stopped_reason"] == "approval_required"

    def test_closed_task_session_refused(self, tmp_path: Path) -> None:
        session_id = "session-agentic-004"
        task = _task_with_session(tmp_path, session_id)
        TaskStore(tmp_path).save(task.model_copy(update={"status": "closed"}))
        result = _invoke(tmp_path, ["resume", task.task_id, "--json"])
        assert result.exit_code == 1
        assert "closed" in json.loads(result.output)["error"]

    def test_resume_never_auto_runs_apply_commit_or_rollback(self, tmp_path: Path) -> None:
        session_id = "session-agentic-005"
        _task_with_session(tmp_path, session_id)
        _journal(tmp_path, session_id)
        with patch("safecode.cli_resume.AgentLoop") as MockLoop:
            result = _invoke(tmp_path, ["resume", "--json"])
        assert result.exit_code == 0
        assert not MockLoop.called

    def test_missing_journal_does_not_crash(self, tmp_path: Path) -> None:
        task = _task_with_session(tmp_path, "session-agentic-006")
        result = _invoke(tmp_path, ["resume", task.task_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert "agentic_session" not in data
