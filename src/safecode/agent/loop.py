"""Bounded interactive agent loop primitives."""

from __future__ import annotations

import warnings
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from typing import TYPE_CHECKING

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall
from safecode.agent.multi_tool_turn import MultiToolTurnResult, MultiToolTurnRunner

if TYPE_CHECKING:
    from safecode.llm.cost import TokenUsage
    from safecode.agent.conversation import ConversationBuffer
from safecode.agent.orchestrator import AgentOrchestrator
from safecode.agent.pending_action import PatchPendingAction, StopForUserAction, ToolPendingAction
from safecode.agent.schemas import AgentNativeToolCallResponse, AgentStopForUserResponse, AgentToolIntentResponse, RecoverableContractFailure
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
from safecode.utils.time import utc_now_iso
from safecode.agent.step_model import (
    TypedAgentStep,
    TypedAgentStepResult,
    classify_step_from_pending_action,
)
from safecode.agent.validation import ValidationLoop


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
        self._last_tool_intent_identity: tuple[str, str, str, str] | None = None
        self._last_tool_intent_count = 0
        self._last_typed_step: TypedAgentStep | None = None
        self._last_typed_result: TypedAgentStepResult | None = None
        self.no_validate = False
        self.auto_edit = auto_edit
        self.full_auto = full_auto
        self.command_delay_ms = command_delay_ms
        self.plan_mode = plan_mode
        self._native_write_count = 0
        self._session_observations: list[str] = []
        self._compactor: object | None = None
        self.no_clarify = no_clarify

    def session_cost(self) -> "TokenUsage | None":
        """Return accumulated token usage for this session, or None if no data."""
        try:
            return self._cost_accumulator.load()
        except Exception:
            return None

    @property
    def last_typed_result(self) -> TypedAgentStepResult | None:
        """The typed result from the most recently completed step, or None."""
        return self._last_typed_result

    def _get_compactor(self, session_id: str) -> object:
        """Return or lazily create the ContextCompactor for this session."""
        if self._compactor is None:
            from safecode.context.compaction import ContextCompactor
            self._compactor = ContextCompactor(
                self.llm_client,
                self.project_root,
                session_id,
                max_context_tokens=self.config.max_context_chars // 4,  # chars→rough tokens
            )
        return self._compactor

    def _maybe_compact_context(self, session_id: str) -> str | None:
        """If accumulated observations exceed the configured budget ratio, compact them.

        Returns the compact summary string if compaction occurred, else None.
        Prints a notice to stdout when compaction fires.
        """
        if not self._session_observations:
            return None
        compactor = self._get_compactor(session_id)
        combined = "\n".join(self._session_observations)
        token_estimate = len(combined) // 4  # rough chars-to-tokens
        if not compactor.should_compact(token_estimate):
            return None
        try:
            import sys
            result = compactor.compact(self._session_observations)
            notice = (
                f"[Context compacted: ~{result.tokens_before} → ~{result.tokens_after} tokens "
                f"({result.observations_archived} observations archived)]"
            )
            print(notice, file=sys.stdout, flush=True)
            self._session_observations = []  # reset after compaction
            return result.summary
        except RuntimeError as exc:
            warnings.warn(f"compaction failed (context preserved): {exc}", RuntimeWarning, stacklevel=2)
            return None

    def _build_dispatcher(self) -> NativeToolDispatcher:
        """Create a NativeToolDispatcher with native tools registered.

        When auto_edit=True or full_auto=True, write tools are registered with
        approved=True so they execute immediately without blocking.
        In full_auto mode, run_command is registered with a delay for Ctrl-C abort.
        Policy gates (high-risk blocking) still apply via ShellRunner.
        In plan_mode, only read/search/reference tools are registered.
        """
        from safecode.agent.read_tools import register_read_tools
        from safecode.agent.write_tools import register_write_tools
        from safecode.agent.command_tool import register_command_tool
        from safecode.mcp.native_bridge import register_mcp_tools
        from safecode.agent.find_references_tool import register_find_references_tool

        dispatcher = NativeToolDispatcher()
        register_read_tools(dispatcher, self.project_root)
        if self.plan_mode:
            register_mcp_tools(dispatcher, self.project_root)
            register_find_references_tool(dispatcher, self.project_root)
            return dispatcher
        write_approved = self.auto_edit or self.full_auto
        register_write_tools(dispatcher, self.project_root, approved=write_approved)
        cmd_delay = self.command_delay_ms if self.full_auto else -1
        register_command_tool(dispatcher, self.project_root, full_auto_delay_ms=cmd_delay)
        register_mcp_tools(dispatcher, self.project_root)  # v5.4.0: MCP native tool bridge
        register_find_references_tool(dispatcher, self.project_root)  # v6.9.0
        return dispatcher

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
            _COMPACT_THRESHOLD = 12  # turns before attempting LLM summary
            if conversation.turn_count() > _COMPACT_THRESHOLD:
                try:
                    conversation.compact_with_llm(self.llm_client)
                except Exception:
                    pass  # fail-soft: keep existing buffer

        # v6.7.1: pass conversation-mentioned files for context bonus
        conv_files = conversation.mentioned_files() if conversation else None
        context = self.context_collector.collect(query=state.goal, conversation_files=conv_files)
        context = self._enrich_with_subagent_findings(state.session_id, context)

        # Compact old observations before the next LLM call so long sessions stay usable.
        compact_summary = self._maybe_compact_context(state.session_id)
        if compact_summary:
            context["compacted_session_summary"] = compact_summary

        dispatcher = self._build_dispatcher()
        tool_specs = dispatcher.specs()

        # File count guard: if in auto_edit mode and session write count is near limit, pause.
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
            # Single retry on recoverable failures.
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
            """Feed tool results back to model; return next calls or None to stop."""
            enriched = {**ctx, "tool_results": obs_text}
            next_raw = self.llm_client.choose_tool_native(
                state.goal,
                enriched,
                tool_specs,
                step=state.current_step,
                conversation_history=conv_history,
            )
            if isinstance(next_raw, list):
                return [
                    NativeToolCall(tool_name=c.tool_name, input=c.input, call_id=c.call_id)
                    for c in next_raw
                ]
            return None  # stop_for_user or RCF → end the turn

        runner = MultiToolTurnRunner(dispatcher)
        turn_result = runner.run_turn(native_calls, llm_next_fn=_llm_next_fn, context=context)

        # Count write tool calls for file count guard.
        write_tool_names = {"edit_file", "write_file"}
        write_calls = sum(1 for r in turn_result.tool_calls if r.tool_name in write_tool_names)
        self._native_write_count += write_calls

        # Keep tool observations available for later compaction.
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
            saved.session_id,
            saved.current_step,
            observation,
            pending_action,
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=stopped_for_approval,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation, stopped_for_approval=stopped_for_approval)

    def _classify_and_record(
        self,
        step_index: int,
        pending_action: dict[str, object] | None,
        observation: str,
        stopped_for_approval: bool,
        failure_category: str | None = None,
        session_id: str | None = None,
    ) -> tuple[TypedAgentStep, TypedAgentStepResult]:
        """Classify one completed step into typed step + result and cache them.

        When session_id is provided, also persists typed events to the journal
        (v4.11.1). Journal writes are best-effort and never raise.
        """
        typed_step, typed_result = classify_step_from_pending_action(
            step_index=step_index,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=stopped_for_approval,
            failure_category=failure_category,
        )
        self._last_typed_step = typed_step
        self._last_typed_result = typed_result
        if session_id:
            try:
                self.journal.record_typed_step(session_id, typed_step)
                self.journal.record_typed_result(session_id, typed_result)
            except Exception:
                pass
            try:
                self._record_step_journal_entry(
                    session_id=session_id,
                    step_index=step_index,
                    pending_action=pending_action,
                    observation=observation,
                    typed_result=typed_result,
                )
            except Exception:
                pass
        return typed_step, typed_result

    def _record_step_journal_entry(
        self,
        *,
        session_id: str,
        step_index: int,
        pending_action: dict[str, object] | None,
        observation: str,
        typed_result: TypedAgentStepResult,
    ) -> None:
        from safecode.state.step_journal import StepJournalEntry, StepJournalStore

        action = pending_action or {}
        raw_files = action.get("files", [])
        files_changed = [str(item) for item in raw_files] if isinstance(raw_files, (list, tuple)) else []
        tool_name = str(action.get("tool_name") or action.get("route") or "")
        StepJournalStore(self.project_root).append(
            StepJournalEntry(
                step_id=f"{session_id}:{step_index}",
                session_id=session_id,
                step_index=step_index,
                action_type=typed_result.kind,
                tool_name=tool_name,
                files_changed=files_changed,
                outcome=typed_result.status,
                summary=observation,
            )
        )

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
            self.journal.record_action(saved.session_id, saved.current_step, tool_choice.message, saved.pending_action)
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
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation)

    def run(
        self,
        goal: str | None = None,
        max_steps: int = 20,  # B8 fix: raised from 5 to 20 for real coding tasks
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
                    steps.append(AgentStepResult(state=state, observation=f"Validation: {validation_result.status}"))
                    if validation_result.status == "repair_proposed":
                        stopped_reason = "approval_required"
                    else:
                        stopped_reason = validation_result.stop_reason or validation_result.status
                    break
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

        self._write_session_summary(
            session_id=state.session_id,
            goal=goal or state.goal or "",
            steps=steps,
            stopped_reason=stopped_reason,
            started_at=run_started_at,
        )

        return AgentRunResult(state=state, steps=steps, stopped_reason=stopped_reason)

    def _clarify_if_needed(self, goal: str) -> "AgentRunResult | None":
        """Return an AgentRunResult requesting clarification if the goal is ambiguous.

        Returns None when clarification is not needed (normal execution continues).
        Fails closed: any error returns None (don't block the agent).
        """
        try:
            from safecode.agent.clarify import detect_ambiguity
            result = detect_ambiguity(goal, self.llm_client)
            if not result.needs_clarification:
                return None
            # Build a minimal stopped state
            state = self.store.load()
            if state is None:
                state = self._start_planned_session(goal)
            pending_action: dict[str, object] = {
                "type": "clarification",
                "route": "needs_clarification",
                "requires_approval": True,
                "questions": list(result.questions),
                "reason": result.reason,
            }
            updated = state.model_copy(update={
                "pending_action": pending_action,
                "last_observation": (
                    "Goal is ambiguous. Please answer the following questions before proceeding:\n"
                    + "\n".join(f"- {q}" for q in result.questions)
                ),
                "status": "waiting_for_user",
            })
            saved = self.store.save(updated)
            clarify_step = AgentStepResult(
                state=saved,
                observation=saved.last_observation or "",
                stopped_for_approval=True,
            )
            self._write_session_summary(
                session_id=saved.session_id,
                goal=goal,
                steps=[clarify_step],
                stopped_reason="needs_clarification",
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            return AgentRunResult(
                state=saved,
                steps=[clarify_step],
                stopped_reason="needs_clarification",
            )
        except Exception:
            return None

    def _prepend_session_memory(self, goal: str | None) -> str | None:
        """Load approved facts, project notes, and recent session summaries; prepend to goal."""
        try:
            from safecode.memory.session_store import SessionSummaryStore
            from safecode.memory.summary import format_memory_context
            from safecode.memory.facts import ProjectFactStore
            from safecode.memory.facade import MemoryFacade
            blocks: list[str] = []
            facts_ctx = ProjectFactStore(self._sac_dir).approved_context()
            if facts_ctx:
                blocks.append(facts_ctx)
            notes = MemoryFacade(self.project_root).read_project_notes()
            if notes and notes.strip():
                notes_trimmed = notes.strip()[:800]
                blocks.append(f"## Project Notes\n{notes_trimmed}")
            summaries = SessionSummaryStore(self._sac_dir).load_recent(limit=3)
            session_ctx = format_memory_context(summaries)
            if session_ctx:
                blocks.append(session_ctx)
            if not blocks:
                return goal
            prefix = "\n\n".join(blocks)
            return f"{prefix}\n\n{goal}" if goal else prefix
        except Exception:
            return goal

    def _write_session_summary(
        self,
        session_id: str,
        goal: str,
        steps: list[AgentStepResult],
        stopped_reason: str,
        started_at: str,
    ) -> None:
        """Write a bounded session summary to the session store after run() completes."""
        try:
            from safecode.memory.session_store import SessionSummaryStore
            from safecode.memory.summary import build_session_summary
            observations = [s.observation for s in steps if s.observation]
            approved = sum(1 for s in steps if s.stopped_for_approval)
            summary = build_session_summary(
                session_id=session_id,
                goal=goal,
                step_observations=observations,
                stopped_reason=stopped_reason,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc).isoformat(),
                approved_patches=approved,
            )
            SessionSummaryStore(self._sac_dir).append(summary)
            # Propose conventions inferred from this session (fail-closed)
            try:
                from safecode.memory.facts import ProjectFactStore
                ProjectFactStore(self._sac_dir).propose_from_session_summary(
                    commands_run=summary.commands_run,
                    touched_files=summary.touched_files,
                )
            except Exception:
                pass
        except Exception:
            pass

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
            self.store.save(updated)
        return result

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
        # B9 fix: track stuck-loop even when no current task is set.
        # Inside a task scope: abort after 3 identical intents (existing behaviour).
        # Outside a task scope: emit a RuntimeWarning but do NOT abort, so that
        # existing taskless agent sessions (e.g. tests) still run to completion.
        has_current_task = TaskStore(self.project_root).current_id() is not None
        identity = self._tool_intent_identity(routed)
        if identity == self._last_tool_intent_identity:
            self._last_tool_intent_count += 1
        else:
            self._last_tool_intent_identity = identity
            self._last_tool_intent_count = 1
        if self._last_tool_intent_count < 3:
            return None

        # Always log the warning (B9: visible even outside task scope).
        import warnings
        observation = "Aborted: repeated identical tool intent detected."
        RuntimeLogger(self.project_root, self.config).write(
            "error",
            "agent.loop",
            observation,
            failure_category=FailureCategory.LOOP_STUCK.value,
            details={"session_id": state.session_id, "has_current_task": has_current_task},
        )

        if not has_current_task:
            # B9: outside task scope — warn but do not abort the session.
            warnings.warn(
                f"loop_stuck detected outside task scope after {self._last_tool_intent_count} identical intents",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

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
            session_id=saved.session_id,
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
            session_id=saved.session_id,
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
                session_id=saved.session_id,
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
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=observation, stopped_for_approval=False)

        patch_files = [block.file_path.as_posix() for block in edit_result.proposal.blocks]

        # v6.8.0: classify tier and auto-apply when safe.
        from safecode.agent.approval_tier import ApprovalTier, classify_proposal
        tier = classify_proposal(edit_result.proposal, self.config)

        # v6.26: full_auto also auto-applies CONFIRM tier (not just AUTO).
        # GATE tier always stops for approval regardless of mode.
        auto_apply_condition = (
            (tier == ApprovalTier.AUTO and (self.auto_edit or self.full_auto))
            or (tier == ApprovalTier.CONFIRM and self.full_auto)
        )
        if auto_apply_condition:
            # Apply immediately — checkpoint + audit still happen inside apply().
            try:
                orch = AgentOrchestrator(self.project_root, llm_client=self.llm_client)
                apply_result = orch.apply(edit_result.proposal)
                tier_label = tier.value
                observation = (
                    f"Auto-applied patch (tier={tier_label}, full_auto={self.full_auto}): "
                    f"{', '.join(patch_files)}. "
                    f"Checkpoint {apply_result.checkpoint.checkpoint_id} created. "
                    "Run 'sac rollback --last' to undo."
                )
                auto_action: dict[str, object] = {
                    "type": "patch",
                    "route": routed.route,
                    "requires_approval": False,
                    "reason": "auto_applied",
                    "patch_id": edit_result.proposal.id,
                    "files": patch_files,
                    "tier": tier.value,
                }
                updated = state.model_copy(
                    update={
                        "current_step": state.current_step + 1,
                        "pending_action": auto_action,
                        "last_observation": observation,
                        "status": "active",
                        "last_error": None,
                    }
                )
                saved = self.store.save(updated)
                self.journal.record_patch_proposal(
                    saved.session_id,
                    saved.current_step,
                    observation,
                    {"patch_id": edit_result.proposal.id, "files": patch_files, "tier": tier.value},
                )
                self._classify_and_record(
                    step_index=saved.current_step,
                    pending_action=auto_action,
                    observation=observation,
                    stopped_for_approval=False,
                    session_id=saved.session_id,
                )
                return AgentStepResult(state=saved, observation=observation, stopped_for_approval=False)
            except Exception as exc:
                # Auto-apply failed; fall through to normal confirm flow.
                RuntimeLogger(self.project_root, self.config).error(
                    "agent.loop", f"Auto-apply failed, falling back to confirm: {exc}", exc=exc
                )
                tier = ApprovalTier.CONFIRM

        # CONFIRM or GATE — stop for user approval (gate carries extra warning).
        gate_note = " [GATE: high-sensitivity change]" if tier == ApprovalTier.GATE else ""
        approved_patch_action = PatchPendingAction(
            route=routed.route,
            requires_approval=True,
            reason=f"patch_proposal_awaiting_approval{gate_note}",
            patch_id=edit_result.proposal.id,
            pending_patch_path=str(edit_result.pending_patch_path),
            files=tuple(patch_files),
        )
        pending_action = approved_patch_action.to_dict()
        pending_action["tier"] = tier.value
        observation = (
            f"Patch proposal created: {edit_result.pending_patch_path.name} "
            f"(patch_id={edit_result.proposal.id}, tier={tier.value}){gate_note}. "
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
                "tier": tier.value,
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
            session_id=saved.session_id,
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
            session_id=saved.session_id,
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

    def resume_from(self, session_id: str) -> AgentSessionState:
        """Reconstruct in-memory state from the existing agent journal.

        Passive only: this restores session state and never re-runs apply,
        commit, rollback, validation, or repair.
        """
        events = self.journal.read(session_id)
        current = self.store.load()
        if current is not None and current.session_id == session_id:
            state = current
        else:
            plan = self.journal.latest_plan(session_id) or []
            goal = ""
            for event in events:
                if event.type == "plan":
                    raw_goal = event.payload.get("goal")
                    goal = str(raw_goal) if raw_goal is not None else ""
                    break
            if not goal:
                goal = current.goal if current is not None else "resumed agent session"
            now = utc_now_iso()
            state = AgentSessionState(
                session_id=session_id,
                goal=goal,
                plan=plan,
                current_step=0,
                pending_action=None,
                last_observation="Agent session resumed from journal.",
                status="active",
                last_error=None,
                created_at=now,
                updated_at=now,
            )

        pending_index: int | None = None
        last_summary = state.last_observation
        for event in events:
            if event.type != "typed_result":
                continue
            raw = event.payload.get("typed_result")
            if not isinstance(raw, dict):
                continue
            if raw.get("summary"):
                last_summary = str(raw.get("summary"))
            status = str(raw.get("status", ""))
            if status in {"waiting_for_user", "interrupted"} and pending_index is None:
                try:
                    pending_index = int(raw.get("step_index", event.step or 0))
                except (TypeError, ValueError):
                    pending_index = event.step or 0

        update: dict[str, object] = {
            "plan": self.journal.latest_plan(session_id) or state.plan,
            "current_step": pending_index if pending_index is not None else state.current_step,
            "last_observation": last_summary or "Agent session resumed from journal.",
            "last_error": None,
        }
        if state.status not in {"closed", "completed"}:
            update["status"] = "waiting_for_user" if pending_index is not None else "active"
        return self.store.save(state.model_copy(update=update))

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
