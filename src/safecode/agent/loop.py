"""Bounded interactive agent loop primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.agent.tools import ToolIntentRouter
from safecode.state.journal import AgentJournalStore


DEFAULT_PLAN = [
    "Inspect current project state and user goal.",
    "Choose the next safe tool action.",
    "Stop before any write or command execution that needs approval.",
]


@dataclass(frozen=True)
class AgentStepResult:
    """Result of advancing one agent step."""

    state: AgentSessionState
    observation: str
    stopped_for_approval: bool = False


@dataclass(frozen=True)
class AgentRunResult:
    """Result of advancing a bounded number of agent steps."""

    state: AgentSessionState
    steps: list[AgentStepResult]
    stopped_reason: str


class AgentLoop:
    """Deterministic stepping loop used before model-driven autonomy."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.store = AgentSessionStore(project_root)
        self.journal = AgentJournalStore(project_root)

    def step(self, goal: str | None = None) -> AgentStepResult:
        """Advance exactly one safe session step."""
        state = self.store.load()
        if state is None:
            if not goal:
                raise FileNotFoundError("No agent session found. Provide a goal or run 'sac agent start'.")
            state = self.store.start(goal, plan=DEFAULT_PLAN)
        elif goal and goal != state.goal:
            state = self.store.start(goal, plan=DEFAULT_PLAN)
        elif not state.plan:
            state = state.model_copy(update={"plan": DEFAULT_PLAN})
            self.journal.record_plan(state.session_id, state.goal, DEFAULT_PLAN)

        if state.current_step >= len(state.plan):
            updated = state.model_copy(
                update={
                    "status": "completed",
                    "pending_action": None,
                    "last_observation": "Plan already completed.",
                }
            )
            saved = self.store.save(updated)
            self.journal.record_final_summary(
                saved.session_id,
                saved.last_observation,
                {
                    "status": saved.status,
                    "current_step": saved.current_step,
                    "plan_items": len(saved.plan),
                },
            )
            return AgentStepResult(state=saved, observation=saved.last_observation)

        plan_item = state.plan[state.current_step]
        routed = ToolIntentRouter().route(
            {
                "type": "read",
                "target": "project_context",
                "description": plan_item,
            }
        )
        pending_action = {
            **routed.intent.model_dump(exclude_none=True),
            "route": routed.route,
            "executable_now": str(routed.executable_now).lower(),
            "reason": routed.reason,
        }
        observation = f"Step {state.current_step + 1}: {plan_item}"
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None,
            }
        )
        saved = self.store.save(updated)
        self.journal.record_action(
            saved.session_id,
            saved.current_step,
            observation,
            pending_action,
        )
        return AgentStepResult(state=saved, observation=observation)

    def run(self, goal: str | None = None, max_steps: int = 5) -> AgentRunResult:
        """Advance up to ``max_steps`` safe steps."""
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")

        steps: list[AgentStepResult] = []
        next_goal = goal
        stopped_reason = "max_steps_reached"
        state: AgentSessionState | None = self.store.load()

        for _ in range(max_steps):
            result = self.step(next_goal)
            steps.append(result)
            state = result.state
            next_goal = None
            if result.stopped_for_approval:
                stopped_reason = "approval_required"
                break
            if state.status == "completed":
                stopped_reason = "completed"
                break

        if state is None:
            # This is only reachable if step() behavior changes.
            raise FileNotFoundError("No agent session found.")

        return AgentRunResult(state=state, steps=steps, stopped_reason=stopped_reason)
