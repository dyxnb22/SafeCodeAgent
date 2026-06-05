"""Bounded interactive agent loop primitives."""

from __future__ import annotations

import warnings
import time
from dataclasses import dataclass
from pathlib import Path

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.agent.pending_action import PatchPendingAction, StopForUserAction, ToolPendingAction
from safecode.agent.schemas import AgentStopForUserResponse, AgentToolIntentResponse, RecoverableContractFailure
from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.agent.tools import RoutedToolIntent, ToolIntentRouter
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.context.redactor import redact_secrets
from safecode.core.failure_category import FailureCategory
from safecode.llm.factory import create_llm_client
from safecode.mcp.loop_executor import MCPApprovedWriteExecutor, MCPReadToolExecutor
from safecode.subagents.executor import SubagentDispatchExecutor
from safecode.subagents.journal_adapter import findings_from_journal_events, merge_journal_subagent_findings
from safecode.subagents.merge_policy import merge_subagent_findings
from safecode.subagents.synthesis import synthesize_findings
from safecode.mcp.proposal import MCPWriteProposal, MCPWriteProposalStore
from safecode.state.journal import AgentJournalStore
from safecode.task.budget import TaskBudgetStore, record_budget_exceeded
from safecode.task.state import TaskIteration
from safecode.task.store import TaskStore
from safecode.logs.runtime import RuntimeLogger
from safecode.agent.step_model import (
    TypedAgentStep,
    TypedAgentStepResult,
    classify_step_from_pending_action,
)


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

    def __init__(self, project_root: Path, llm_client: object | None = None) -> None:
        self.project_root = project_root
        self.config = SafeCodeConfig.load(project_root)
        self.context_collector = ContextCollector(project_root, self.config)
        self.llm_client = llm_client if llm_client is not None else create_llm_client(self.config)
        self.store = AgentSessionStore(project_root)
        self.journal = AgentJournalStore(project_root)
        self._last_tool_intent_identity: tuple[str, str, str, str] | None = None
        self._last_tool_intent_count = 0
        self._last_typed_step: TypedAgentStep | None = None
        self._last_typed_result: TypedAgentStepResult | None = None

    @property
    def last_typed_result(self) -> TypedAgentStepResult | None:
        """The typed result from the most recently completed step, or None."""
        return self._last_typed_result

    def _classify_and_record(
        self,
        step_index: int,
        pending_action: dict[str, object] | None,
        observation: str,
        stopped_for_approval: bool,
        failure_category: str | None = None,
    ) -> tuple[TypedAgentStep, TypedAgentStepResult]:
        """Classify one completed step into typed step + result and cache them."""
        typed_step, typed_result = classify_step_from_pending_action(
            step_index=step_index,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=stopped_for_approval,
            failure_category=failure_category,
        )
        self._last_typed_step = typed_step
        self._last_typed_result = typed_result
        return typed_step, typed_result

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
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=None,
                observation=saved.last_observation,
                stopped_for_approval=False,
            )
            return AgentStepResult(state=saved, observation=saved.last_observation)

        plan_item = state.plan[state.current_step]
        context = self.context_collector.collect(query=f"{state.goal}\n{plan_item}")
        context = self._enrich_with_subagent_findings(state.session_id, context)
        tool_choice = self.llm_client.choose_tool(state.goal, context)

        # Bounded retry: one retry for recoverable contract-shaped failures only.
        # Do NOT retry: policy blocks, validation failures, user-stop, or hard violations.
        if isinstance(tool_choice, RecoverableContractFailure):
            self.journal.record_loop_retry(
                state.session_id,
                state.current_step,
                f"Recoverable contract failure; retrying step {state.current_step}.",
                {
                    "method": tool_choice.method,
                    "message": tool_choice.message,
                    "retry_attempt": 1,
                },
            )
            tool_choice = self.llm_client.choose_tool(state.goal, context)
            # If the retry also returns a recoverable failure, treat as permanent.
            if isinstance(tool_choice, RecoverableContractFailure):
                observation = (
                    f"Contract failure after retry: {tool_choice.method}: {tool_choice.message}"
                )
                updated = state.model_copy(
                    update={
                        "pending_action": None,
                        "last_observation": observation,
                        "status": "active",
                        "last_error": observation,
                    }
                )
                saved = self.store.save(updated)
                self.journal.record_failure(
                    saved.session_id,
                    observation,
                    {"error": observation, "after_retry": True, "failure_category": "model_output_invalid"},
                )
                RuntimeLogger(self.project_root, self.config).write(
                    "error",
                    "agent.loop",
                    observation,
                    failure_category=FailureCategory.MODEL_OUTPUT_INVALID.value,
                    details={"session_id": saved.session_id},
                )
                self._classify_and_record(
                    step_index=saved.current_step,
                    pending_action=saved.pending_action,
                    observation=observation,
                    stopped_for_approval=False,
                    failure_category="model_output_invalid",
                )
                return AgentStepResult(state=saved, observation=observation, stopped_for_approval=False)

        if isinstance(tool_choice, AgentStopForUserResponse):
            stop_action = StopForUserAction(
                reason=tool_choice.reason,
                message=tool_choice.message,
                requires_approval=tool_choice.requires_approval,
            )
            updated = state.model_copy(
                update={
                    "pending_action": stop_action.to_dict(),
                    "last_observation": tool_choice.message,
                    "status": "waiting_for_user",
                    "last_error": None,
                }
            )
            saved = self.store.save(updated)
            self.journal.record_action(saved.session_id, saved.current_step, tool_choice.message, saved.pending_action)
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=saved.pending_action,
                observation=tool_choice.message,
                stopped_for_approval=True,
            )
            return AgentStepResult(state=saved, observation=tool_choice.message, stopped_for_approval=True)

        if not isinstance(tool_choice, AgentToolIntentResponse):
            raise ValueError(f"Unsupported tool choice response: {tool_choice.type}")

        routed = ToolIntentRouter().route(tool_choice.intent.model_dump(exclude_none=True))
        stuck = self._abort_if_stuck_tool_intent(state, routed)
        if stuck is not None:
            return stuck

        if routed.executable_now and routed.route == "mcp.call_readonly":
            return self._execute_mcp_readonly_step(plan_item, state, routed)

        if routed.executable_now and routed.route == "subagent.dispatch":
            return self._execute_subagent_dispatch_step(plan_item, state, routed)

        if routed.route == "mcp.propose" and not routed.executable_now:
            approved = self._find_approved_write_proposal(routed.intent.tool_name or "")
            if approved is not None:
                return self._execute_mcp_approved_write_step(plan_item, state, routed, approved.proposal_id)

        if routed.route == "patch.propose" and not routed.executable_now:
            return self._execute_patch_proposal_step(plan_item, state, routed)

        tool_action = ToolPendingAction(
            type=routed.intent.type,
            route=routed.route,
            executable_now=routed.executable_now,
            requires_approval=routed.intent.requires_approval,
            reason=routed.reason,
            tool_name=routed.intent.tool_name or "",
            description=routed.intent.description or "",
            intent_fields=routed.intent.model_dump(exclude_none=True),
        )
        pending_action = tool_action.to_dict()
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
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
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
        started_at = time.monotonic()
        budget_task_id = TaskStore(self.project_root).current_id()
        budget = TaskBudgetStore(self.project_root).load(budget_task_id) if budget_task_id else None
        step_budget = min(max_steps, budget.steps) if budget is not None else max_steps

        for _ in range(step_budget):
            if budget is not None and time.monotonic() - started_at >= budget.time_seconds:
                state = self._record_budget_failure(state, budget_task_id, "time_seconds")
                stopped_reason = "budget_exceeded"
                break
            result = self.step(next_goal)
            steps.append(result)
            state = result.state
            next_goal = None
            if result.stopped_for_approval:
                stopped_reason = "approval_required"
                break
            if state.status == "aborted":
                stopped_reason = "loop_stuck" if state.last_error and "loop_stuck" in state.last_error else "aborted"
                break
            if state.status == "completed":
                stopped_reason = "completed"
                break
        else:
            if budget is not None and step_budget < max_steps:
                state = self._record_budget_failure(state, budget_task_id, "steps")
                stopped_reason = "budget_exceeded"

        if state is None:
            # This is only reachable if step() behavior changes.
            raise FileNotFoundError("No agent session found.")

        return AgentRunResult(state=state, steps=steps, stopped_reason=stopped_reason)

    def _tool_intent_identity(self, routed: RoutedToolIntent) -> tuple[str, str, str, str]:
        intent = routed.intent
        return (
            intent.type,
            intent.target or "",
            intent.tool_name or "",
            intent.description or "",
        )

    def _abort_if_stuck_tool_intent(
        self, state: AgentSessionState, routed: RoutedToolIntent
    ) -> AgentStepResult | None:
        if TaskStore(self.project_root).current_id() is None:
            return None
        identity = self._tool_intent_identity(routed)
        if identity == self._last_tool_intent_identity:
            self._last_tool_intent_count += 1
        else:
            self._last_tool_intent_identity = identity
            self._last_tool_intent_count = 1
        if self._last_tool_intent_count < 3:
            return None

        observation = "Aborted: repeated identical tool intent detected."
        updated = state.model_copy(
            update={
                "pending_action": None,
                "last_observation": observation,
                "status": "aborted",
                "last_error": "loop_stuck: repeated identical tool intent",
            }
        )
        saved = self.store.save(updated)
        self.journal.record_failure(
            saved.session_id,
            observation,
            {
                "failure_category": "loop_stuck",
                "intent_identity": list(identity),
                "consecutive_count": self._last_tool_intent_count,
            },
        )
        RuntimeLogger(self.project_root, self.config).write(
            "error",
            "agent.loop",
            observation,
            failure_category=FailureCategory.LOOP_STUCK.value,
            details={"session_id": saved.session_id},
        )
        self._record_loop_stuck_on_current_task()
        return AgentStepResult(state=saved, observation=observation)

    def _record_loop_stuck_on_current_task(self) -> None:
        try:
            task_store = TaskStore(self.project_root)
            task_id = task_store.current_id()
            if not task_id:
                return
            state = task_store.load(task_id)
            if state is None:
                return
            iteration = TaskIteration(
                iteration_index=state.next_iteration_index(),
                event="loop",
                mode="tool_intent",
                status="failed",
                failure_category="loop_stuck",
            )
            task_store.save(state.model_copy(update={"iterations": list(state.iterations) + [iteration]}))
        except Exception:
            pass

    def _record_budget_failure(
        self,
        state: AgentSessionState | None,
        task_id: str | None,
        budget_name: str,
    ) -> AgentSessionState:
        observation = f"Budget exceeded: {budget_name}."
        if task_id:
            try:
                record_budget_exceeded(self.project_root, task_id, budget_name)
            except Exception:
                pass

        current = state or self.store.load()
        if current is None:
            raise FileNotFoundError("No agent session found.")
        updated = current.model_copy(
            update={
                "pending_action": None,
                "last_observation": observation,
                "status": "aborted",
                "last_error": f"budget_exceeded: {budget_name}",
            }
        )
        saved = self.store.save(updated)
        self.journal.record_failure(
            saved.session_id,
            observation,
            {"failure_category": "budget_exceeded", "budget": budget_name, "task_id": task_id or ""},
        )
        RuntimeLogger(self.project_root, self.config).write(
            "error",
            "agent.loop",
            observation,
            failure_category=FailureCategory.BUDGET_EXCEEDED.value,
            details={"task_id": task_id or "", "budget": budget_name},
        )
        return saved

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
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
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
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
        )
        return AgentStepResult(state=saved, observation=observation)

    def _execute_patch_proposal_step(
        self, plan_item: str, state: AgentSessionState, routed: RoutedToolIntent
    ) -> AgentStepResult:
        """Generate a pending patch proposal via AgentOrchestrator and stop for approval.

        Fail closed: if a pending patch already exists, stop for approval without
        overwriting. If proposal generation fails, record the error without modifying
        any business/source files.
        """
        pending_patch_path = self.project_root / ".sac" / "pending_patch.json"

        if pending_patch_path.exists():
            observation = (
                "A pending patch already exists and requires review before a new one "
                "can be created. Run 'sac apply' to review and apply it, or "
                "'sac rollback' to discard it."
            )
            existing_patch_action = PatchPendingAction(
                route=routed.route,
                requires_approval=True,
                reason="pending_patch_already_exists",
                pending_patch_path=str(pending_patch_path),
                target=str(routed.intent.target or ""),
            )
            pending_action: dict[str, object] = existing_patch_action.to_dict()
            updated = state.model_copy(
                update={
                    "pending_action": pending_action,
                    "last_observation": observation,
                    "status": "waiting_for_user",
                    "last_error": observation,
                }
            )
            saved = self.store.save(updated)
            self.journal.record_action(
                saved.session_id,
                saved.current_step,
                observation,
                pending_action,
            )
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=pending_action,
                observation=observation,
                stopped_for_approval=True,
            )
            return AgentStepResult(state=saved, observation=observation, stopped_for_approval=True)

        try:
            edit_result = AgentOrchestrator(self.project_root, llm_client=self.llm_client).edit(state.goal)
        except Exception as exc:
            observation = f"Patch proposal failed: {exc}"
            failed_patch_action = PatchPendingAction(
                route=routed.route,
                requires_approval=True,
                reason="patch_proposal_failed",
                target=str(routed.intent.target or ""),
            )
            err_action: dict[str, object] = failed_patch_action.to_dict()
            updated = state.model_copy(
                update={
                    "pending_action": err_action,
                    "last_observation": observation,
                    "status": "active",
                    "last_error": observation,
                }
            )
            saved = self.store.save(updated)
            self.journal.record_failure(saved.session_id, observation, {"error": str(exc), "failure_category": "patch_parse_failed"})
            RuntimeLogger(self.project_root, self.config).error(
                "agent.loop",
                observation,
                exc=exc,
                failure_category=FailureCategory.PATCH_PARSE_FAILED.value,
            )
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=err_action,
                observation=observation,
                stopped_for_approval=False,
                failure_category="patch_parse_failed",
            )
            return AgentStepResult(state=saved, observation=observation, stopped_for_approval=False)

        patch_files = [block.file_path.as_posix() for block in edit_result.proposal.blocks]
        approved_patch_action = PatchPendingAction(
            route=routed.route,
            requires_approval=True,
            reason="patch_proposal_awaiting_approval",
            patch_id=edit_result.proposal.id,
            pending_patch_path=str(edit_result.pending_patch_path),
            files=tuple(patch_files),
        )
        pending_action = approved_patch_action.to_dict()
        observation = (
            f"Patch proposal created: {edit_result.pending_patch_path.name} "
            f"(patch_id={edit_result.proposal.id}). "
            "Review with 'sac apply' — target files are not modified until you approve."
        )
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "waiting_for_user",
                "last_error": None,
            }
        )
        saved = self.store.save(updated)
        self.journal.record_patch_proposal(
            saved.session_id,
            saved.current_step,
            observation,
            {
                "patch_id": edit_result.proposal.id,
                "pending_patch_path": str(edit_result.pending_patch_path),
                "files": patch_files,
                "scope_status": (
                    edit_result.scope_result.status
                    if edit_result.scope_result is not None
                    else "no_prediction"
                ),
            },
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=True,
        )
        return AgentStepResult(state=saved, observation=observation, stopped_for_approval=True)

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
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
        )
        return AgentStepResult(state=saved, observation=observation)

    def _enrich_with_subagent_findings(self, session_id: str, context: dict) -> dict:
        """Inject merged subagent findings and synthesis into planning context.

        Secrets are redacted before injection. Parent calls synthesize_findings
        before consuming the merged list (T-3.4.2-A). Fail closed: any error
        leaves context unchanged and emits a warning without interrupting the loop.
        """
        try:
            events = self.journal.read(session_id)
            # Get raw findings for synthesis (T-3.4.2-A).
            findings = findings_from_journal_events(events)
            merged = merge_subagent_findings(findings)
            if merged.source_task_ids or merged.blocked_task_ids or merged.errors:
                # Consumer-side redaction is defense-in-depth (producer-side is primary).
                # Warn if consumer pass still changes text, indicating a gap upstream.
                redacted_summary = redact_secrets(merged.summary)
                redacted_observations = [redact_secrets(o) for o in merged.observations]
                redacted_errors = [redact_secrets(e) for e in merged.errors]
                if (
                    redacted_summary != merged.summary
                    or redacted_observations != list(merged.observations)
                    or redacted_errors != list(merged.errors)
                ):
                    warnings.warn(
                        "consumer-side redaction changed merged subagent text; "
                        "producer-side redaction may have missed a secret",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                context["subagent_findings"] = {
                    "summary": redacted_summary,
                    "observations": redacted_observations,
                    "files_inspected": merged.files_inspected,
                    "source_task_ids": merged.source_task_ids,
                    "blocked_task_ids": merged.blocked_task_ids,
                    "errors": redacted_errors,
                }

                # T-3.4.2-A: synthesize before parent consumes merged findings.
                try:
                    synthesis = synthesize_findings(findings, self.llm_client)
                    context["subagent_synthesis"] = {
                        "summary": synthesis.summary,
                        "key_findings": synthesis.key_findings,
                        "risks": synthesis.risks,
                        "source_task_ids": synthesis.source_task_ids,
                        "used_fallback": synthesis.used_fallback,
                    }
                except Exception as syn_exc:
                    warnings.warn(
                        f"subagent synthesis failed (merged findings preserved): {type(syn_exc).__name__}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
        except Exception as exc:
            warnings.warn(
                f"subagent enrichment failed (context unchanged): {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
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
