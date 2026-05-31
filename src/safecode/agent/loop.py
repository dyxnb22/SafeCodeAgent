"""Bounded interactive agent loop primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.agent.schemas import AgentStopForUserResponse, AgentToolIntentResponse
from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.agent.tools import ToolIntentRouter
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.llm.factory import create_llm_client
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
        self.config = SafeCodeConfig.load(project_root)
        self.context_collector = ContextCollector(project_root, self.config)
        self.llm_client = create_llm_client(self.config)
        self.store = AgentSessionStore(project_root)
        self.journal = AgentJournalStore(project_root)

    def step(self, goal: str | None = None) -> AgentStepResult:
        """Advance exactly one safe session step."""
        state = self.store.load()
        if state is None:
            if not goal:
                raise FileNotFoundError("No agent session found. Provide a goal or run 'sac agent start'.")
            state = self._start_planned_session(goal)
        elif goal and goal != state.goal:
            state = self._start_planned_session(goal)
        elif not state.plan:
            planned = self._plan_steps(state.goal)
            state = state.model_copy(update={"plan": planned, "current_step": 0})
            state = self.store.save(state)
            self.journal.record_plan(state.session_id, state.goal, planned)

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
        tool_choice = self.llm_client.choose_tool(
            state.goal,
            self.context_collector.collect(query=f"{state.goal}\n{plan_item}"),
        )
        if isinstance(tool_choice, AgentStopForUserResponse):
            updated = state.model_copy(
                update={
                    "pending_action": {
                        "type": tool_choice.type,
                        "reason": tool_choice.reason,
                        "message": tool_choice.message,
                        "requires_approval": str(tool_choice.requires_approval).lower(),
                    },
                    "last_observation": tool_choice.message,
                    "status": "waiting_for_user",
                    "last_error": None,
                }
            )
            saved = self.store.save(updated)
            self.journal.record_action(saved.session_id, saved.current_step, tool_choice.message, saved.pending_action)
            return AgentStepResult(state=saved, observation=tool_choice.message, stopped_for_approval=True)

        if not isinstance(tool_choice, AgentToolIntentResponse):
            raise ValueError(f"Unsupported tool choice response: {tool_choice.type}")

        routed = ToolIntentRouter().route(tool_choice.intent.model_dump(exclude_none=True))
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

    def _start_planned_session(self, goal: str) -> AgentSessionState:
        """Create a session using the current LLM planning contract."""
        return self.store.start(goal, plan=self._plan_steps(goal))

    def _plan_steps(self, goal: str) -> list[str]:
        """Return LLM-planned steps with a deterministic fallback."""
        try:
            plan = self.llm_client.plan(goal, self.context_collector.collect(query=goal))
            return list(plan.steps)
        except Exception:
            return list(DEFAULT_PLAN)
