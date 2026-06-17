"""Session lifecycle and planning helpers for AgentLoop (v6.29).

Extracted from loop.py as _PlannerMixin. Covers:
- _start_planned_session / _plan_steps  (goal → SessionState with LLM plan)
- resume_from                           (journal replay → SessionState)
- _clarify_if_needed                    (ambiguity detection)
- _prepend_session_memory               (cross-session memory prefix)
- _write_session_summary                (post-run summary persistence)

All methods type-hint ``self`` as ``AgentLoop`` (guarded by TYPE_CHECKING)
so that attribute access is type-safe, while no circular import occurs at
runtime.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from safecode.agent.loop_types import AgentRunResult, AgentStepResult
from safecode.agent.session import AgentSessionState
from safecode.utils.time import utc_now_iso

if TYPE_CHECKING:
    from safecode.agent.loop import AgentLoop


#: Fallback plan used when the LLM plan call fails.
DEFAULT_PLAN = [
    "Inspect current project state and user goal.",
    "Choose the next safe tool action.",
    "Stop before any write or command execution that needs approval.",
]


class _PlannerMixin:
    """Session lifecycle and planning methods — mixed into AgentLoop."""

    # ------------------------------------------------------------------
    # Public: resume
    # ------------------------------------------------------------------

    def resume_from(self: "AgentLoop", session_id: str) -> AgentSessionState:
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

    # ------------------------------------------------------------------
    # Internal: session start / plan
    # ------------------------------------------------------------------

    def _start_planned_session(self: "AgentLoop", goal: str) -> AgentSessionState:
        """Create a session using the current LLM planning contract."""
        return self.store.start(goal, plan=self._plan_steps(goal))

    def _plan_steps(self: "AgentLoop", goal: str) -> list[str]:
        """Return LLM-planned steps with a deterministic fallback."""
        try:
            plan = self.llm_client.plan(goal, self.context_collector.collect(query=goal))
            return list(plan.steps)
        except Exception:
            return list(DEFAULT_PLAN)

    # ------------------------------------------------------------------
    # Internal: clarification
    # ------------------------------------------------------------------

    def _clarify_if_needed(self: "AgentLoop", goal: str) -> "AgentRunResult | None":
        """Return an AgentRunResult requesting clarification if the goal is ambiguous.

        Returns None when clarification is not needed (normal execution continues).
        Fails closed: any error returns None (don't block the agent).
        """
        try:
            from safecode.agent.clarify import detect_ambiguity
            result = detect_ambiguity(goal, self.llm_client)
            if not result.needs_clarification:
                return None
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

    # ------------------------------------------------------------------
    # Internal: memory prefix
    # ------------------------------------------------------------------

    def _prepend_session_memory(self: "AgentLoop", goal: str | None) -> str | None:
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

    # ------------------------------------------------------------------
    # Internal: post-run summary
    # ------------------------------------------------------------------

    def _write_session_summary(
        self: "AgentLoop",
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
