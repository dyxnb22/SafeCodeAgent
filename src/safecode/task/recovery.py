"""Task recovery helpers for resume and durable interruption (experimental, v4.4+)."""

from __future__ import annotations

from pathlib import Path

from safecode.agent.session import AgentSessionStore
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.state.journal import AgentJournalStore
from safecode.task.state import TaskIteration, TaskState
from safecode.task.store import TaskStore
from safecode.task.wiring import get_or_create_current_task
from safecode.utils.time import utc_now_iso


def most_recent_resumable_task(store: TaskStore) -> TaskState | None:
    """Return CURRENT if resumable, otherwise newest open/interrupted task."""
    current_id = store.current_id()
    if current_id:
        current = store.load(current_id)
        if current is not None and current.status in {"open", "interrupted", "applied"}:
            return current

    for state in store.list():
        if state.status in {"open", "interrupted"}:
            return state
    return None


def mark_task_interrupted(
    project_root: Path,
    *,
    command_name: str,
    hint: str = "",
    task_id: str | None = None,
) -> TaskState | None:
    """Persist an interrupted marker for SIGINT without touching pending patches."""
    store = TaskStore(project_root)
    try:
        state = store.load(task_id) if task_id else get_or_create_current_task(project_root, command_name, hint)
    except Exception:
        return None
    if state is None:
        return None

    iteration = TaskIteration(
        iteration_index=state.next_iteration_index(),
        event="interrupted",
        mode=command_name,
        status="interrupted",
        failure_category="interrupted",
    )
    updated = state.model_copy(
        update={
            "status": "interrupted",
            "iterations": list(state.iterations) + [iteration],
        }
    )
    try:
        store.save(updated)
        store.set_current(updated.task_id)
    except Exception:
        return updated

    try:
        session_store = AgentSessionStore(project_root)
        session = session_store.load()
        if session is not None:
            saved_session = session_store.save(
                session.model_copy(
                    update={
                        "status": "interrupted",
                        "last_error": f"Interrupted during sac {command_name}.",
                        "last_observation": f"Session interrupted during sac {command_name}.",
                    }
                )
            )
            AgentJournalStore(project_root).record_failure(
                saved_session.session_id,
                f"Interrupted during sac {command_name}.",
                {
                    "failure_category": "interrupted",
                    "task_id": updated.task_id,
                    "command": command_name,
                },
            )
    except Exception:
        pass

    try:
        AuditLogger(project_root).write(
            AuditEvent(
                type="task_interrupted",
                timestamp=utc_now_iso(),
                status="failed",
                message=f"Task interrupted during sac {command_name}.",
                metadata={"failure_category": "interrupted"},
            ),
            task_id=updated.task_id,
        )
    except Exception:
        pass

    return updated
