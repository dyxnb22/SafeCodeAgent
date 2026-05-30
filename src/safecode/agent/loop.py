"""Bounded interactive agent loop primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.agent.session import AgentSessionState, AgentSessionStore


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


class AgentLoop:
    """Deterministic stepping loop used before model-driven autonomy."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.store = AgentSessionStore(project_root)

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

        if state.current_step >= len(state.plan):
            updated = state.model_copy(
                update={
                    "status": "completed",
                    "pending_action": None,
                    "last_observation": "Plan already completed.",
                }
            )
            saved = self.store.save(updated)
            return AgentStepResult(state=saved, observation=saved.last_observation)

        plan_item = state.plan[state.current_step]
        pending_action = {
            "type": "read",
            "status": "planned",
            "description": plan_item,
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
        return AgentStepResult(state=saved, observation=observation)
