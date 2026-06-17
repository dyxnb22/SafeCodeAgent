"""Tests for v6.32 dynamic re-planning."""

from __future__ import annotations

from pathlib import Path

from safecode.agent.loop import AgentLoop
from safecode.agent.schemas import AgentAnswer, AgentPlanResponse


class _ReplanningLLM:
    def __init__(self) -> None:
        self.plan_calls: list[tuple[str, dict]] = []

    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        self.plan_calls.append((goal, context))
        if "Previous plan failed" in goal:
            return AgentPlanResponse(
                goal=goal,
                steps=["Inspect failing diagnostics", "Apply a different repair", "Run validation"],
            )
        return AgentPlanResponse(goal=goal, steps=["Initial broken approach"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError


def _loop(tmp_path: Path, *, full_auto: bool = True) -> tuple[AgentLoop, _ReplanningLLM]:
    llm = _ReplanningLLM()
    loop = AgentLoop(tmp_path, llm_client=llm, full_auto=full_auto, no_clarify=True)
    return loop, llm


def test_try_replan_generates_new_plan_after_repeated_validation_failure(tmp_path: Path) -> None:
    loop, llm = _loop(tmp_path)
    state = loop.store.start("Fix parse_config", plan=["Try local edit", "Run tests"])
    loop.journal.record_action(state.session_id, 0, "Applied first patch", {"type": "patch"})
    loop.journal.record_failure(
        state.session_id,
        "Validation failed in test; tail_hash=abc",
        {"failure_category": "validation_failed"},
    )

    assert loop._try_replan(
        state,
        "tests still fail with ImportError",
        repair_attempts=2,
        failure_category="validation_fail",
    ) is True

    saved = loop.store.load()
    assert saved is not None
    assert saved.replan_count == 1
    assert saved.current_step == 0
    assert saved.status == "active"
    assert saved.plan == ["Inspect failing diagnostics", "Apply a different repair", "Run validation"]
    assert "Previous plan failed" in llm.plan_calls[-1][0]
    assert llm.plan_calls[-1][1]["replan_failure_category"] == "validation_fail"
    assert "Applied first patch" in llm.plan_calls[-1][1]["replan_attempted_summary"]


def test_try_replan_requires_full_auto(tmp_path: Path) -> None:
    loop, _ = _loop(tmp_path, full_auto=False)
    state = loop.store.start("Fix tests", plan=["old"])

    assert loop._try_replan(
        state,
        "failure",
        repair_attempts=2,
        failure_category="validation_fail",
    ) is False
    assert loop.store.load().plan == ["old"]  # type: ignore[union-attr]


def test_try_replan_requires_repeated_repairs(tmp_path: Path) -> None:
    loop, _ = _loop(tmp_path)
    state = loop.store.start("Fix tests", plan=["old"])

    assert loop._try_replan(
        state,
        "failure",
        repair_attempts=1,
        failure_category="validation_fail",
    ) is False
    assert loop.store.load().replan_count == 0  # type: ignore[union-attr]


def test_try_replan_caps_session_replans(tmp_path: Path) -> None:
    loop, _ = _loop(tmp_path)
    state = loop.store.start("Fix tests", plan=["old"]).model_copy(update={"replan_count": 2})
    state = loop.store.save(state)

    assert loop._try_replan(
        state,
        "failure",
        repair_attempts=2,
        failure_category="validation_fail",
    ) is False
    assert loop.store.load().plan == ["old"]  # type: ignore[union-attr]

