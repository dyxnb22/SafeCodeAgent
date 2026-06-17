"""Bounded interactive agent loop primitives (v6.29 refactored).

AgentLoop is now composed from four focused mixin classes:

  _PlannerMixin   (loop_planner.py)   — session lifecycle, planning, memory
  _BudgetMixin    (loop_budget.py)    — stuck-loop detection, budget, compaction
  _JournalMixin   (loop_journal.py)   — typed-step classification and recording
  _DispatcherMixin(loop_dispatcher.py)— build_dispatcher, _execute_*_step routing

This file retains only the core stepping logic:
  __init__      — wires up all shared state
  native_step   — native-tool protocol step (P1, v5.1.0)
  step          — JSON-schema protocol step
  run           — bounded multi-step loop
  + validation helpers (_should_validate_after_step, _run_validation_after_apply)

Re-exports:
  AgentStepResult, AgentRunResult  — from loop_types (backward-compatible)
  DEFAULT_PLAN                     — from loop_planner (backward-compatible)
"""

from __future__ import annotations

import time
import warnings
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from safecode.agent.loop_budget import _BudgetMixin
from safecode.agent.loop_dispatcher import _DispatcherMixin
from safecode.agent.loop_journal import _JournalMixin
from safecode.agent.loop_planner import DEFAULT_PLAN, _PlannerMixin
from safecode.agent.loop_types import AgentRunResult, AgentStepResult
from safecode.agent.multi_tool_turn import MultiToolTurnRunner
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall
from safecode.agent.pending_action import PatchPendingAction, StopForUserAction, ToolPendingAction
from safecode.agent.schemas import (
    AgentNativeToolCallResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
)
from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.agent.step_model import TypedAgentStep, TypedAgentStepResult, classify_step_from_pending_action
from safecode.agent.tools import RoutedToolIntent, ToolIntentRouter
from safecode.agent.validation import ValidationLoop
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.context.redactor import redact_secrets
from safecode.core.failure_category import FailureCategory
from safecode.config import SafeCodeConfig
from safecode.llm.factory import create_llm_client
from safecode.logs.runtime import RuntimeLogger
from safecode.mcp.proposal import MCPWriteProposal, MCPWriteProposalStore
from safecode.state.journal import AgentJournalStore
from safecode.task.budget import TaskBudgetStore, record_budget_exceeded
from safecode.task.state import TaskIteration
from safecode.task.store import TaskStore
from safecode.utils.time import utc_now_iso

if TYPE_CHECKING:
    from safecode.llm.cost import TokenUsage
    from safecode.agent.conversation import ConversationBuffer


# ---------------------------------------------------------------------------
# Shared result types — re-exported here for backward compatibility.
# All existing ``from safecode.agent.loop import AgentStepResult`` imports work.
# ---------------------------------------------------------------------------
__all__ = [
    "AgentLoop",
    "AgentStepResult",
    "AgentRunResult",
    "DEFAULT_PLAN",
]


class AgentLoop(_PlannerMixin, _BudgetMixin, _JournalMixin, _DispatcherMixin):
    """Deterministic stepping loop used before model-driven autonomy.

    Architecture (v6.29):
    ┌─────────────────────────────────────────────────────────┐
    │  AgentLoop (core step / run logic)                      │
    ├───────────────┬────────────────┬────────────────────────┤
    │ _PlannerMixin │ _BudgetMixin   │ _JournalMixin          │
    │ loop_planner  │ loop_budget    │ loop_journal            │
    │ session start │ stuck-loop     │ classify & record       │
    │ plan steps    │ budget fail    │ step journal            │
    │ resume_from   │ compaction     │                         │
    │ clarify       │                │                         │
    │ memory prefix │                │                         │
    ├───────────────┴────────────────┴────────────────────────┤
    │ _DispatcherMixin  (loop_dispatcher.py)                  │
    │ build_dispatcher  _execute_mcp_readonly_step            │
    │ _execute_patch_proposal_step  _execute_subagent_step    │
    │ _execute_mcp_approved_write_step  _enrich_subagent      │
    └─────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        project_root: Path,
        llm_client: object | None = None,
        *,
        auto_edit: bool = False,
        full_auto: bool = False,
        command_delay_ms: int = 500,
        no_clarify: bool = False,
        plan_mode: bool = False,
    ) -> None:
        from uuid import uuid4
        from safecode.llm.cost import SessionCostAccumulator

        self.project_root = project_root
        self.config = SafeCodeConfig.load(project_root)
        self.context_collector = ContextCollector(project_root, self.config)
        self._sac_dir = project_root / self.config.sac_dir
        self._cost_session_id = uuid4().hex
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = create_llm_client(
                self.config,
                session_id=self._cost_session_id,
                sac_dir=self._sac_dir,
            )
        self._cost_accumulator = SessionCostAccumulator(self._sac_dir, self._cost_session_id)
        self.store = AgentSessionStore(project_root)
        self.journal = AgentJournalStore(project_root)
        # Stuck-loop state (owned by _BudgetMixin methods)
        self._last_tool_intent_identity: tuple[str, str, str, str] | None = None
        self._last_tool_intent_count = 0
        # Typed step cache (owned by _JournalMixin methods)
        self._last_typed_step: TypedAgentStep | None = None
        self._last_typed_result: TypedAgentStepResult | None = None
        # Validation
        self.no_validate = False
        # Trust mode flags
        self.auto_edit = auto_edit
        self.full_auto = full_auto
        self.command_delay_ms = command_delay_ms
        self.plan_mode = plan_mode
        # Clarification gate
        self.no_clarify = no_clarify
        # Write count guard (owned by native_step)
        self._native_write_count = 0
        # Observation accumulator for context compaction (_BudgetMixin)
        self._session_observations: list[str] = []
        # Lazy ContextCompactor instance (_BudgetMixin)
        self._compactor: object | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def session_cost(self) -> "TokenUsage | None":
        """Return accumulated session token cost, or None when unavailable."""
        try:
            return self._cost_accumulator.load()
        except Exception:
            return None

    @property
    def last_typed_result(self) -> TypedAgentStepResult | None:
        return self._last_typed_result

    # ------------------------------------------------------------------
    # Native-tool step (P1, v5.1.0)
    # ------------------------------------------------------------------

    def native_step(
        self,
        goal: str | None = None,
        *,
        conversation: "ConversationBuffer | None" = None,
    ) -> "AgentStepResult":
        """Advance one step via the native tool protocol (P1, v5.1.0).

        Unlike step() which uses the JSON contract, native_step() calls
        choose_tool_native() and dispatches results through MultiToolTurnRunner.
        The model's tool calls are dispatched, results fed back as context, and
        the loop continues until the model emits a stop or the turn cap is reached.

        Falls back to step() when the LLM client does not support native tools.
        """
        if not hasattr(self.llm_client, "choose_tool_native"):
            return self.step(goal)

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
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=None,
                observation=saved.last_observation,
                stopped_for_approval=False,
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=saved.last_observation)

        # v6.24: LLM-backed conversation compaction when buffer is long.
        if conversation is not None:
            _COMPACT_THRESHOLD = 12
            if conversation.turn_count() > _COMPACT_THRESHOLD:
                try:
                    conversation.compact_with_llm(self.llm_client)
                except Exception:
                    pass

        # v6.7.1: pass conversation-mentioned files for context bonus
        conv_files = conversation.mentioned_files() if conversation else None
        context = self.context_collector.collect(query=state.goal, conversation_files=conv_files)
        context = self._enrich_with_subagent_findings(state.session_id, context)

        compact_summary = self._maybe_compact_context(state.session_id)
        if compact_summary:
            context["compacted_session_summary"] = compact_summary

        dispatcher = self._build_dispatcher()
        tool_specs = dispatcher.specs()

        # File count guard: auto_edit sessions pause when write count nears the limit.
        _AUTO_EDIT_FILE_GUARD = 10
        if self.auto_edit and self._native_write_count >= _AUTO_EDIT_FILE_GUARD:
            observation = (
                f"About to edit more than {_AUTO_EDIT_FILE_GUARD} files this session. "
                "Pausing for review. Approve with /continue or type another goal."
            )
            stop_action = StopForUserAction(
                reason="file_count_guard",
                message=observation,
                requires_approval=True,
            )
            pending_action = stop_action.to_dict()
            updated = state.model_copy(
                update={
                    "pending_action": pending_action,
                    "last_observation": observation,
                    "status": "waiting_for_user",
                    "last_error": None,
                }
            )
            saved = self.store.save(updated)
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=pending_action,
                observation=observation,
                stopped_for_approval=True,
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=observation, stopped_for_approval=True)

        # Call model with native tool protocol.
        conv_history = conversation.to_messages() if conversation and not conversation.is_empty() else None
        raw_result = self.llm_client.choose_tool_native(
            state.goal, context, tool_specs,
            step=state.current_step,
            conversation_history=conv_history,
        )

        if isinstance(raw_result, RecoverableContractFailure):
            raw_result = self.llm_client.choose_tool_native(
                state.goal, context, tool_specs,
                step=state.current_step,
                conversation_history=conv_history,
            )
            if isinstance(raw_result, RecoverableContractFailure):
                observation = f"Native tool contract failure after retry: {raw_result.message}"
                updated = state.model_copy(
                    update={
                        "pending_action": None,
                        "last_observation": observation,
                        "status": "active",
                        "last_error": observation,
                    }
                )
                saved = self.store.save(updated)
                self._classify_and_record(
                    step_index=saved.current_step,
                    pending_action=None,
                    observation=observation,
                    stopped_for_approval=False,
                    failure_category="model_output_invalid",
                    session_id=saved.session_id,
                )
                return AgentStepResult(state=saved, observation=observation)

        if isinstance(raw_result, AgentStopForUserResponse):
            stop_action = StopForUserAction(
                reason=raw_result.reason,
                message=raw_result.message,
                requires_approval=raw_result.requires_approval,
            )
            pending_action = stop_action.to_dict()
            updated = state.model_copy(
                update={
                    "pending_action": pending_action,
                    "last_observation": raw_result.message,
                    "status": "waiting_for_user",
                    "last_error": None,
                }
            )
            saved = self.store.save(updated)
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=pending_action,
                observation=raw_result.message,
                stopped_for_approval=True,
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=raw_result.message, stopped_for_approval=True)

        # raw_result is list[AgentNativeToolCallResponse] — dispatch via MultiToolTurnRunner.
        native_calls = [
            NativeToolCall(tool_name=c.tool_name, input=c.input, call_id=c.call_id)
            for c in raw_result
        ]

        def _llm_next_fn(obs_text: str, ctx: dict):
            enriched = {**ctx, "tool_results": obs_text}
            next_raw = self.llm_client.choose_tool_native(
                state.goal, enriched, tool_specs,
                step=state.current_step,
                conversation_history=conv_history,
            )
            if isinstance(next_raw, list):
                return [
                    NativeToolCall(tool_name=c.tool_name, input=c.input, call_id=c.call_id)
                    for c in next_raw
                ]
            return None

        runner = MultiToolTurnRunner(dispatcher)
        turn_result = runner.run_turn(native_calls, llm_next_fn=_llm_next_fn, context=context)

        write_tool_names = {"edit_file", "write_file"}
        write_calls = sum(1 for r in turn_result.tool_calls if r.tool_name in write_tool_names)
        self._native_write_count += write_calls

        if turn_result.observations:
            self._session_observations.extend(turn_result.observations)

        observation = turn_result.context_block() or f"Native turn: {turn_result.stopped_reason}"
        pending_action: dict[str, object] = {
            "type": "native_turn",
            "route": "native.dispatch",
            "stopped_reason": turn_result.stopped_reason,
            "tool_calls_count": str(len(turn_result.tool_calls)),
            "cap_hit": str(turn_result.cap_hit).lower(),
            "write_calls": str(write_calls),
        }
        stopped_for_approval = turn_result.stopped_reason in {"stop_for_user", "error"} and not self.auto_edit

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
            saved.session_id, saved.current_step, observation, pending_action,
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=stopped_for_approval,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation, stopped_for_approval=stopped_for_approval)

    # ------------------------------------------------------------------
    # JSON-schema step (legacy protocol)
    # ------------------------------------------------------------------

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
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=saved.last_observation)

        plan_item = state.plan[state.current_step]
        context = self.context_collector.collect(query=f"{state.goal}\n{plan_item}")
        context = self._enrich_with_subagent_findings(state.session_id, context)
        tool_choice = self.llm_client.choose_tool(state.goal, context)

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
                    saved.session_id, observation,
                    {"error": observation, "after_retry": True, "failure_category": "model_output_invalid"},
                )
                RuntimeLogger(self.project_root, self.config).write(
                    "error", "agent.loop", observation,
                    failure_category=FailureCategory.MODEL_OUTPUT_INVALID.value,
                    details={"session_id": saved.session_id},
                )
                self._classify_and_record(
                    step_index=saved.current_step,
                    pending_action=saved.pending_action,
                    observation=observation,
                    stopped_for_approval=False,
                    failure_category="model_output_invalid",
                    session_id=saved.session_id,
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
            self.journal.record_action(
                saved.session_id, saved.current_step, tool_choice.message, saved.pending_action
            )
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=saved.pending_action,
                observation=tool_choice.message,
                stopped_for_approval=True,
                session_id=saved.session_id,
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
        self.journal.record_action(saved.session_id, saved.current_step, observation, pending_action)
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation)

    # ------------------------------------------------------------------
    # Multi-step run
    # ------------------------------------------------------------------

    def run(
        self,
        goal: str | None = None,
        max_steps: int = 20,
        *,
        on_step: "Callable[[AgentStepResult], None] | None" = None,
        conversation: "ConversationBuffer | None" = None,
    ) -> AgentRunResult:
        """Advance up to ``max_steps`` safe steps.

        If *on_step* is provided, it is called after each step with the
        AgentStepResult, enabling real-time progress display (v4.18+).
        """
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")

        # Pre-task clarification gate (v6.8.0): stop early when goal is ambiguous.
        if goal and not self.no_clarify:
            clarification = self._clarify_if_needed(goal)
            if clarification is not None:
                return clarification

        steps: list[AgentStepResult] = []
        next_goal = self._prepend_session_memory(goal)
        stopped_reason = "max_steps_reached"
        state: AgentSessionState | None = self.store.load()
        run_started_at = datetime.now(timezone.utc).isoformat()
        started_at = time.monotonic()
        budget_task_id = TaskStore(self.project_root).current_id()
        budget = TaskBudgetStore(self.project_root).load(budget_task_id) if budget_task_id else None
        step_budget = min(max_steps, budget.steps) if budget is not None else max_steps

        for _ in range(step_budget):
            if budget is not None and time.monotonic() - started_at >= budget.time_seconds:
                state = self._record_budget_failure(state, budget_task_id, "time_seconds")
                stopped_reason = "budget_exceeded"
                break
            if hasattr(self.llm_client, "choose_tool_native"):
                result = self.native_step(next_goal, conversation=conversation)
            else:
                result = self.step(next_goal)
            steps.append(result)
            state = result.state
            next_goal = None
            if on_step is not None:
                try:
                    on_step(result)
                except Exception:
                    pass
            if self._should_validate_after_step():
                validation_result = self._run_validation_after_apply(state)
                state = self.store.load() or state
                if validation_result.status in {
                    "repair_proposed",
                    "repair_failed",
                    "loop_no_progress",
                    "max_repair_iterations",
                    "skipped",
                }:
                    steps.append(
                        AgentStepResult(state=state, observation=f"Validation: {validation_result.status}")
                    )
                    if validation_result.status == "repair_proposed":
                        stopped_reason = "approval_required"
                    else:
                        stopped_reason = validation_result.stop_reason or validation_result.status
                    break
            if result.stopped_for_approval:
                stopped_reason = "approval_required"
                break
            if state.status == "aborted":
                stopped_reason = (
                    "loop_stuck"
                    if state.last_error and "loop_stuck" in state.last_error
                    else "aborted"
                )
                break
            if state.status == "completed":
                stopped_reason = "completed"
                break
        else:
            if budget is not None and step_budget < max_steps:
                state = self._record_budget_failure(state, budget_task_id, "steps")
                stopped_reason = "budget_exceeded"

        if state is None:
            raise FileNotFoundError("No agent session found.")

        self._write_session_summary(
            session_id=state.session_id,
            goal=goal or state.goal or "",
            steps=steps,
            stopped_reason=stopped_reason,
            started_at=run_started_at,
        )
        return AgentRunResult(state=state, steps=steps, stopped_reason=stopped_reason)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _should_validate_after_step(self) -> bool:
        if self.no_validate:
            return False
        last = self._last_typed_result
        return last is not None and last.kind == "apply" and last.status in {"approved", "success"}

    def _run_validation_after_apply(self, state: AgentSessionState):
        validation = ValidationLoop(self.project_root, journal=self.journal)
        result = validation.run_after_apply(
            session_id=state.session_id,
            step_index=state.current_step,
            goal=state.goal,
        )
        if result.status == "repair_proposed":
            pending_action = {
                "type": "patch",
                "route": "patch.propose",
                "requires_approval": True,
                "reason": "validation_repair_awaiting_approval",
                "repair_iteration": str(result.repair_iterations),
                "failure_tail_hash": result.failure_tail_hash or "",
            }
            updated = state.model_copy(
                update={
                    "pending_action": pending_action,
                    "last_observation": "Validation failed; repair patch proposed for review.",
                    "status": "waiting_for_user",
                    "last_error": None,
                }
            )
            self.store.save(updated)
        elif result.status in {"repair_failed", "loop_no_progress", "max_repair_iterations"}:
            updated = state.model_copy(
                update={
                    "pending_action": None,
                    "last_observation": f"Validation stopped: {result.status}.",
                    "status": "aborted",
                    "last_error": result.stop_reason or result.status,
                }
            )
            self.store.save(updated)
        elif result.status == "skipped":
            updated = state.model_copy(
                update={
                    "last_observation": result.notes[0] if result.notes else "Validation skipped.",
                    "last_error": None,
                }
            )
        return result
