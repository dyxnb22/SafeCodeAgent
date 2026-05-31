"""Bounded interactive agent loop primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.agent.schemas import AgentStopForUserResponse, AgentToolIntentResponse
from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.agent.tools import RoutedToolIntent, ToolIntentRouter
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.llm.factory import create_llm_client
from safecode.mcp.loop_executor import MCPApprovedWriteExecutor, MCPReadToolExecutor
from safecode.subagents.executor import SubagentDispatchExecutor
from safecode.subagents.journal_adapter import merge_journal_subagent_findings
from safecode.mcp.proposal import MCPWriteProposal, MCPWriteProposalStore
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
        context = self.context_collector.collect(query=f"{state.goal}\n{plan_item}")
        context = self._enrich_with_subagent_findings(state.session_id, context)
        tool_choice = self.llm_client.choose_tool(state.goal, context)
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

        if routed.executable_now and routed.route == "mcp.call_readonly":
            return self._execute_mcp_readonly_step(plan_item, state, routed)

        if routed.executable_now and routed.route == "subagent.dispatch":
            return self._execute_subagent_dispatch_step(plan_item, state, routed)

        if routed.route == "mcp.propose" and not routed.executable_now:
            approved = self._find_approved_write_proposal(routed.intent.tool_name or "")
            if approved is not None:
                return self._execute_mcp_approved_write_step(plan_item, state, routed, approved.proposal_id)

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

    def _execute_mcp_readonly_step(
        self, plan_item: str, state: AgentSessionState, routed: RoutedToolIntent
    ) -> AgentStepResult:
        """Execute a validated read-only MCP tool call and record the observation."""
        intent = routed.intent
        tool_name = intent.tool_name or ""
        input_json = intent.input_json or {}

        mcp_result = MCPReadToolExecutor(self.project_root).execute(tool_name, input_json)

        step_label = f"Step {state.current_step + 1}: {plan_item}"
        observation = f"{step_label} → MCP [{tool_name}]: {mcp_result.observation}"
        pending_action: dict[str, object] = {
            "type": "mcp",
            "route": routed.route,
            "tool_name": tool_name,
            "executable_now": "true",
            "reason": routed.reason,
            "mcp_success": str(mcp_result.success).lower(),
            "mcp_blocked": str(mcp_result.blocked).lower(),
            "mcp_exit_code": str(mcp_result.exit_code),
        }
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None if mcp_result.success else mcp_result.observation,
            }
        )
        saved = self.store.save(updated)
        call_summary: dict[str, object] = {
            "tool_name": tool_name,
            "server": mcp_result.server,
            "tool": mcp_result.tool,
            "success": mcp_result.success,
            "blocked": mcp_result.blocked,
            "exit_code": mcp_result.exit_code,
            **mcp_result.metadata,
        }
        self.journal.record_mcp_call(
            saved.session_id,
            saved.current_step,
            observation,
            call_summary,
        )
        return AgentStepResult(state=saved, observation=observation)

    def _execute_subagent_dispatch_step(
        self, plan_item: str, state: AgentSessionState, routed: RoutedToolIntent
    ) -> AgentStepResult:
        """Dispatch a read-only subagent investigation and record the structured result."""
        intent = routed.intent
        input_json = intent.input_json or {}
        # Prefer explicit task from input_json; fall back to intent.description.
        task = input_json["task"] if "task" in input_json else (intent.description or "")
        # Pass raw values — no defaults or coercions that would mask missing/invalid args.
        # SubagentDispatchExecutor.execute() accepts Any and gates on ToolCallAdapter.
        scope = input_json.get("scope")
        max_steps = input_json.get("max_steps")

        sub_result = SubagentDispatchExecutor(self.project_root).execute(task, scope, max_steps)

        step_label = f"Step {state.current_step + 1}: {plan_item}"
        observation = f"{step_label} → Subagent [{sub_result.task_id}]: {sub_result.summary}"
        pending_action: dict[str, object] = {
            "type": "subagent",
            "route": routed.route,
            "task_id": sub_result.task_id,
            "executable_now": "true",
            "reason": routed.reason,
            "subagent_success": str(sub_result.success).lower(),
            "subagent_blocked": str(sub_result.blocked).lower(),
        }
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None if sub_result.success else sub_result.summary,
            }
        )
        saved = self.store.save(updated)
        dispatch_summary: dict[str, object] = {
            "task_id": sub_result.task_id,
            "task": task,
            "scope": scope,
            "max_steps": max_steps,
            "summary": sub_result.summary,
            "observations": list(sub_result.observations),
            "files_inspected": list(sub_result.files_inspected),
            "blocked_actions": list(sub_result.blocked_actions),
            "errors": list(sub_result.errors),
            "success": sub_result.success,
            "blocked": sub_result.blocked,
        }
        self.journal.record_subagent_dispatch(
            saved.session_id,
            saved.current_step,
            observation,
            dispatch_summary,
        )
        return AgentStepResult(state=saved, observation=observation)

    def _find_approved_write_proposal(self, tool_name: str) -> MCPWriteProposal | None:
        """Return an approved write proposal matching tool_name, or None."""
        if "." not in tool_name:
            return None
        server, tool = tool_name.split(".", 1)
        if not server or not tool:
            return None
        store = MCPWriteProposalStore(self.project_root, self.config)
        proposal = store.load_pending()
        if proposal is None or proposal.status != "approved":
            return None
        if proposal.server != server or proposal.tool != tool:
            return None
        return proposal

    def _execute_mcp_approved_write_step(
        self,
        plan_item: str,
        state: AgentSessionState,
        routed: RoutedToolIntent,
        proposal_id: str,
    ) -> AgentStepResult:
        """Execute an explicitly approved MCP write tool call and record the observation."""
        intent = routed.intent
        tool_name = intent.tool_name or ""
        input_json = intent.input_json or {}

        mcp_result = MCPApprovedWriteExecutor(self.project_root).execute(
            tool_name, input_json, proposal_id=proposal_id
        )

        step_label = f"Step {state.current_step + 1}: {plan_item}"
        observation = f"{step_label} → MCP write [{tool_name}]: {mcp_result.observation}"
        pending_action: dict[str, object] = {
            "type": "mcp",
            "route": "mcp.execute_approved_write",
            "tool_name": tool_name,
            "executable_now": "true",
            "reason": "approved_write_executed",
            "mcp_success": str(mcp_result.success).lower(),
            "mcp_blocked": str(mcp_result.blocked).lower(),
            "mcp_exit_code": str(mcp_result.exit_code),
        }
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None if mcp_result.success else mcp_result.observation,
            }
        )
        saved = self.store.save(updated)
        call_summary: dict[str, object] = {
            "tool_name": tool_name,
            "server": mcp_result.server,
            "tool": mcp_result.tool,
            "success": mcp_result.success,
            "blocked": mcp_result.blocked,
            "exit_code": mcp_result.exit_code,
            "approved_write": True,
            **mcp_result.metadata,
        }
        self.journal.record_mcp_call(
            saved.session_id,
            saved.current_step,
            observation,
            call_summary,
        )
        return AgentStepResult(state=saved, observation=observation)

    def _enrich_with_subagent_findings(self, session_id: str, context: dict) -> dict:
        """Inject merged subagent findings from this session into planning context.

        Fail closed: any error leaves context unchanged.
        """
        try:
            events = self.journal.read(session_id)
            merged = merge_journal_subagent_findings(events)
            if merged.source_task_ids or merged.blocked_task_ids or merged.errors:
                context["subagent_findings"] = {
                    "summary": merged.summary,
                    "observations": merged.observations,
                    "files_inspected": merged.files_inspected,
                    "source_task_ids": merged.source_task_ids,
                    "blocked_task_ids": merged.blocked_task_ids,
                    "errors": merged.errors,
                }
        except Exception:
            pass
        return context

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
