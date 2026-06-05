"""sac resume command (experimental, v4.4+)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer

from safecode.agent.loop import AgentLoop
from safecode.agent.session import AgentSessionStore
from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.cli_status import next_step
from safecode.context.redactor import redact_secrets
from safecode.state.journal import AgentJournalStore
from safecode.task.recovery import most_recent_resumable_task
from safecode.task.store import TaskStore


def _pending_patch_exists(project_root: Path) -> bool:
    return (project_root / ".sac" / "pending_patch.json").exists()


def _redact_task_id(task_id: str) -> str:
    """Redact secret-like slug fragments without changing the stored task id."""
    redacted = redact_secrets(task_id)
    redacted = re.sub(
        r"(?i)\b(token|password|passwd|secret|api-key|api_key)-[a-z0-9][a-z0-9-]*?(?=-[0-9a-f]{8}\b|$)",
        lambda match: f"{match.group(1)}-[REDACTED]",
        redacted,
    )
    return redacted


def _redact_summary_text(text: str) -> str:
    redacted = redact_secrets(text)
    return re.sub(
        r"(?i)(--(?:password|passwd|token|secret|api-key|api_key)\s+)\S+",
        r"\1[REDACTED]",
        redacted,
    )


def _last_fix_iteration(state: object) -> dict[str, object] | None:
    from safecode.task.state import TaskState

    assert isinstance(state, TaskState)
    for iteration in reversed(state.iterations):
        if iteration.event == "fix":
            return {
                "iteration_index": iteration.iteration_index,
                "mode": iteration.mode,
                "suite": iteration.suite,
                "test_command": _redact_summary_text(iteration.test_command or ""),
                "test_exit_code": iteration.test_exit_code,
                "status": iteration.status,
                "failure_category": iteration.failure_category,
            }
    return None


def _resume_data(project_root: Path, state: object) -> dict[str, object]:
    from safecode.task.state import TaskState

    assert isinstance(state, TaskState)
    patch_exists = _pending_patch_exists(project_root)
    return {
        "task_id": _redact_task_id(state.task_id),
        "goal": _redact_summary_text(state.goal),
        "status": state.status,
        "last_command": _redact_summary_text(state.last_command.command) if state.last_command else None,
        "last_fix_iteration": _last_fix_iteration(state),
        "pending_patch": {
            "exists": patch_exists,
            "task_pending_patch_id": state.pending_patch_id,
            "path": str(project_root / ".sac" / "pending_patch.json") if patch_exists else None,
        },
        "next_step": next_step(state, patch_exists),
    }


def _agentic_session_id(project_root: Path, state: object | None) -> str | None:
    from safecode.task.state import TaskState

    if isinstance(state, TaskState) and state.session_id:
        return state.session_id
    current = AgentSessionStore(project_root).load()
    if current is not None:
        return current.session_id
    return AgentJournalStore(project_root).latest_session_id()


def _agentic_resume_data(project_root: Path, session_id: str | None) -> dict[str, object] | None:
    if not session_id:
        return None
    journal = AgentJournalStore(project_root)
    try:
        events = journal.read(session_id)
    except Exception:
        events = []
    if not events:
        return None
    plan = journal.latest_plan(session_id) or []
    typed = journal.last_typed_result(session_id)
    if _pending_patch_exists(project_root):
        suggested = "apply pending patch"
    elif typed is not None and typed.status == "failed":
        suggested = "rollback"
    elif typed is not None and typed.status in {"waiting_for_user", "interrupted"}:
        suggested = "continue agent run"
    else:
        suggested = "continue agent run"
    return {
        "session_id": session_id,
        "last_plan": plan,
        "last_typed_result": typed.model_dump() if typed is not None else None,
        "suggested_next_safe_step": suggested,
    }


def register(app: typer.Typer) -> None:
    """Register top-level sac resume."""

    @app.command("resume")
    def resume_command(
        task_id: Optional[str] = typer.Argument(None, help="[EXPERIMENTAL] Task id to resume. Defaults to CURRENT/newest resumable task."),
        json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
        continue_agent: bool = typer.Option(False, "--continue-agent", help="[EXPERIMENTAL] Continue the agent loop after passive resume."),
    ) -> None:
        """[EXPERIMENTAL] Resume a task by making it CURRENT and printing the next safe step."""
        project_root = Path.cwd()
        store = TaskStore(project_root)
        state = store.load(task_id) if task_id else most_recent_resumable_task(store)

        if state is None:
            msg = 'No resumable task found. Run: sac task new "<goal>" to start a task.'
            if json_output:
                print(render_json(CLIJSONResponse(command="resume", status="error", error=msg, data={"next_step": msg})))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(code=1)

        if state.status == "closed":
            msg = f"Task is closed and cannot be resumed: {state.task_id}. Run: sac task new \"<goal>\" to start a new task."
            if json_output:
                print(render_json(CLIJSONResponse(command="resume", status="error", error=msg, data={"task_id": state.task_id})))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(code=1)

        if state.status == "interrupted":
            state = state.model_copy(update={"status": "open"})
            store.save(state)
        store.set_current(state.task_id)
        data = _resume_data(project_root, state)
        agentic = _agentic_resume_data(project_root, _agentic_session_id(project_root, state))
        if agentic is not None:
            data["agentic_session"] = agentic

        if continue_agent:
            session_id = str(agentic["session_id"]) if agentic is not None else _agentic_session_id(project_root, state)
            if not session_id:
                msg = "No agentic session found to continue."
                if json_output:
                    print(render_json(CLIJSONResponse(command="resume", status="error", error=msg, data=data)))
                else:
                    console.print(f"[red]{msg}[/red]")
                raise typer.Exit(code=1)
            loop = AgentLoop(project_root)
            loop.resume_from(str(session_id))
            run_result = loop.run(None)
            data["continue_agent"] = {
                "stopped_reason": run_result.stopped_reason,
                "status": run_result.state.status,
                "steps_count": len(run_result.steps),
            }

        if json_output:
            print(render_json(CLIJSONResponse(command="resume", status="success", data=data)))
            return

        console.print("[bold][EXPERIMENTAL] Resume Summary[/bold]")
        console.print(f"task_id: {data['task_id']}")
        console.print(f"goal: {data['goal']}")
        console.print(f"status: {data['status']}")
        console.print(f"last_command: {data['last_command'] or '(none)'}")
        last_fix = data["last_fix_iteration"]
        console.print(f"last_fix_iteration: {last_fix if last_fix is not None else '(none)'}")
        console.print(f"pending_patch: {data['pending_patch']}")
        console.print(f"next_step: {data['next_step']}")
        if agentic is not None:
            console.print("agentic_session:")
            console.print(f"  session_id: {agentic['session_id']}")
            console.print(f"  last_plan: {agentic['last_plan']}")
            console.print(f"  last_typed_result: {agentic['last_typed_result']}")
            console.print(f"  suggested_next_safe_step: {agentic['suggested_next_safe_step']}")

    return resume_command
