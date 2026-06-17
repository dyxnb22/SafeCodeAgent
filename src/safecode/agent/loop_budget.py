"""Budget, stuck-loop detection, and context compaction helpers for AgentLoop (v6.29).

Extracted from loop.py as _BudgetMixin. Covers:
- _get_compactor / _maybe_compact_context  (observation budget compaction)
- _tool_intent_identity                    (identity tuple for stuck-loop detection)
- _abort_if_stuck_tool_intent              (B9: abort or warn on 3 identical intents)
- _record_loop_stuck_on_current_task       (task sidecar update on stuck-loop)
- _record_budget_failure                   (step/time/token budget exceeded)
"""
from __future__ import annotations

import warnings
import sys
from typing import TYPE_CHECKING

from safecode.agent.loop_types import AgentStepResult
from safecode.agent.session import AgentSessionState
from safecode.agent.tools import RoutedToolIntent
from safecode.core.failure_category import FailureCategory
from safecode.logs.runtime import RuntimeLogger
from safecode.task.budget import record_budget_exceeded
from safecode.task.state import TaskIteration
from safecode.task.store import TaskStore

if TYPE_CHECKING:
    from safecode.agent.loop import AgentLoop


class _BudgetMixin:
    """Budget, stuck-loop, and compaction methods — mixed into AgentLoop."""

    # ------------------------------------------------------------------
    # Context compaction
    # ------------------------------------------------------------------

    def _get_compactor(self: "AgentLoop", session_id: str) -> object:
        """Return or lazily create the ContextCompactor for this session."""
        if self._compactor is None:
            from safecode.context.compaction import ContextCompactor
            self._compactor = ContextCompactor(
                self.llm_client,
                self.project_root,
                session_id,
                max_context_tokens=self.config.max_context_chars // 4,
            )
        return self._compactor

    def _maybe_compact_context(self: "AgentLoop", session_id: str) -> str | None:
        """If accumulated observations exceed the configured budget ratio, compact them.

        Returns the compact summary string if compaction occurred, else None.
        Prints a notice to stdout when compaction fires.
        """
        if not self._session_observations:
            return None
        compactor = self._get_compactor(session_id)
        combined = "\n".join(self._session_observations)
        token_estimate = len(combined) // 4
        if not compactor.should_compact(token_estimate):
            return None
        try:
            result = compactor.compact(self._session_observations)
            notice = (
                f"[Context compacted: ~{result.tokens_before} → ~{result.tokens_after} tokens "
                f"({result.observations_archived} observations archived)]"
            )
            print(notice, file=sys.stdout, flush=True)
            self._session_observations = []
            return result.summary
        except RuntimeError as exc:
            warnings.warn(f"compaction failed (context preserved): {exc}", RuntimeWarning, stacklevel=2)
            return None

    # ------------------------------------------------------------------
    # Stuck-loop detection
    # ------------------------------------------------------------------

    def _tool_intent_identity(
        self: "AgentLoop", routed: RoutedToolIntent
    ) -> tuple[str, str, str, str]:
        intent = routed.intent
        return (
            intent.type,
            intent.target or "",
            intent.tool_name or "",
            intent.description or "",
        )

    def _abort_if_stuck_tool_intent(
        self: "AgentLoop",
        state: AgentSessionState,
        routed: RoutedToolIntent,
    ) -> "AgentStepResult | None":
        # B9 fix: track stuck-loop even when no current task is set.
        # Inside a task scope: abort after 3 identical intents (existing behaviour).
        # Outside a task scope: emit a RuntimeWarning but do NOT abort.
        has_current_task = TaskStore(self.project_root).current_id() is not None
        identity = self._tool_intent_identity(routed)
        if identity == self._last_tool_intent_identity:
            self._last_tool_intent_count += 1
        else:
            self._last_tool_intent_identity = identity
            self._last_tool_intent_count = 1
        if self._last_tool_intent_count < 3:
            return None

        observation = "Aborted: repeated identical tool intent detected."
        RuntimeLogger(self.project_root, self.config).write(
            "error",
            "agent.loop",
            observation,
            failure_category=FailureCategory.LOOP_STUCK.value,
            details={"session_id": state.session_id, "has_current_task": has_current_task},
        )

        if not has_current_task:
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

    def _record_loop_stuck_on_current_task(self: "AgentLoop") -> None:
        try:
            task_store = TaskStore(self.project_root)
            task_id = task_store.current_id()
            if not task_id:
                return
            task_state = task_store.load(task_id)
            if task_state is None:
                return
            iteration = TaskIteration(
                iteration_index=task_state.next_iteration_index(),
                event="loop",
                mode="tool_intent",
                status="failed",
                failure_category="loop_stuck",
            )
            task_store.save(
                task_state.model_copy(update={"iterations": list(task_state.iterations) + [iteration]})
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Budget failure
    # ------------------------------------------------------------------

    def _record_budget_failure(
        self: "AgentLoop",
        state: "AgentSessionState | None",
        task_id: "str | None",
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
