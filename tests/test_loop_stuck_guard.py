"""Tests for AgentLoop stuck-loop guard (v4.4.1 T-4.4.1-B)."""

from __future__ import annotations

from safecode.agent.loop import AgentLoop
from safecode.agent.schemas import AgentPlanResponse, AgentToolIntentResponse
from safecode.agent.tools import ToolIntent
from safecode.state.journal import AgentJournalStore
from safecode.task.store import TaskStore


class _SequenceLLM:
    def __init__(self, intents):
        self.intents = list(intents)
        self.index = 0

    def plan(self, goal, context):
        return AgentPlanResponse(goal=goal, steps=["one", "two", "three", "four"])

    def choose_tool(self, goal, context):
        idx = min(self.index, len(self.intents) - 1)
        self.index += 1
        return AgentToolIntentResponse(intent=self.intents[idx], rationale="scripted")


def _read(target: str, description: str = "read"):
    return ToolIntent(type="read", target=target, description=description)


class TestLoopStuckGuard:
    def test_three_identical_intents_abort(self, tmp_path):
        task = TaskStore(tmp_path).create("stuck")
        llm = _SequenceLLM([_read("a.py"), _read("a.py"), _read("a.py")])

        result = AgentLoop(tmp_path, llm_client=llm).run("goal", max_steps=4)

        assert result.stopped_reason == "loop_stuck"
        assert result.state.status == "aborted"
        assert result.state.last_error == "loop_stuck: repeated identical tool intent"
        loaded = TaskStore(tmp_path).load(task.task_id)
        assert loaded is not None
        assert loaded.iterations[-1].failure_category == "loop_stuck"

    def test_two_identical_intents_continue(self, tmp_path):
        TaskStore(tmp_path).create("two ok")
        llm = _SequenceLLM([_read("a.py"), _read("a.py")])

        result = AgentLoop(tmp_path, llm_client=llm).run("goal", max_steps=2)

        assert result.stopped_reason == "max_steps_reached"
        assert result.state.status != "aborted"
        assert result.state.last_error is None

    def test_different_target_resets_count(self, tmp_path):
        TaskStore(tmp_path).create("reset")
        llm = _SequenceLLM([_read("a.py"), _read("a.py"), _read("b.py"), _read("a.py")])

        result = AgentLoop(tmp_path, llm_client=llm).run("goal", max_steps=4)

        assert result.stopped_reason == "max_steps_reached"
        assert result.state.status != "aborted"

    def test_journal_records_loop_stuck_failure_category(self, tmp_path):
        TaskStore(tmp_path).create("journal")
        llm = _SequenceLLM([_read("a.py"), _read("a.py"), _read("a.py")])

        result = AgentLoop(tmp_path, llm_client=llm).run("goal", max_steps=4)
        events = AgentJournalStore(tmp_path).read(result.state.session_id)

        failure = [event for event in events if event.type == "failure"][-1]
        assert failure.payload["details"]["failure_category"] == "loop_stuck"
        assert failure.payload["details"]["consecutive_count"] == 3
