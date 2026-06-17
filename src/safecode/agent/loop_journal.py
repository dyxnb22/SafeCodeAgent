"""Typed-step classification and journal recording helpers for AgentLoop (v6.29).

Extracted from loop.py as _JournalMixin. Covers:
- _classify_and_record      (classify step → TypedAgentStep/Result, cache, persist)
- _record_step_journal_entry (StepJournal append for long-task resume)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from safecode.agent.step_model import (
    TypedAgentStep,
    TypedAgentStepResult,
    classify_step_from_pending_action,
)

if TYPE_CHECKING:
    from safecode.agent.loop import AgentLoop


class _JournalMixin:
    """Typed-step classification and journal recording — mixed into AgentLoop."""

    def _classify_and_record(
        self: "AgentLoop",
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
        self: "AgentLoop",
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
        files_changed = (
            [str(item) for item in raw_files]
            if isinstance(raw_files, (list, tuple))
            else []
        )
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
