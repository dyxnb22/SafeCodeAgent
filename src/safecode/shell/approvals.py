"""In-conversation approval presentation and decisions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from safecode.agent.pending_action import pending_action_from_dict, render_pending_action
from safecode.agent.session import AgentSessionStore


def explain_pending(action_data: dict[str, object]) -> str:
    if action_data.get("type") == "command":
        return f"Command awaiting approval: {action_data.get('command', '')}"
    action = pending_action_from_dict(action_data)
    return render_pending_action(action) if action is not None else "No pending action details are available."


def _patch_path(project_root: Path, session_id: str | None = None) -> Path:
    return (
        project_root / ".sac" / "sessions" / session_id / "pending_patch.json"
        if session_id
        else project_root / ".sac" / "pending_patch.json"
    )


def adopt_legacy_pending_patch(project_root: Path, *, session_id: str) -> bool:
    """Move a legacy global pending patch into the active shell session."""
    legacy_path = _patch_path(project_root)
    scoped_path = _patch_path(project_root, session_id)
    if not legacy_path.exists() or scoped_path.exists():
        return False
    scoped_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy_path), str(scoped_path))
    store = AgentSessionStore(project_root, session_id=session_id)
    state = store.load()
    if state is None:
        state = store.start(
            "Review pending patch",
            ["Review the migrated pending patch."],
            session_id=session_id,
        )
    store.save(state.model_copy(update={
        "status": "waiting_for_approval",
        "pending_action": {
            "type": "patch",
            "route": "legacy.pending_patch",
            "tool_name": "apply_patch",
            "requires_approval": True,
            "reason": "migrated_legacy_pending_patch",
            "pending_patch_path": str(scoped_path),
        },
        "last_observation": "Legacy pending patch migrated into this conversation.",
    }))
    return True


def preview_pending_patch(project_root: Path, *, session_id: str | None = None) -> str | None:
    path = _patch_path(project_root, session_id)
    if not path.exists():
        return None
    from safecode.agent.orchestrator import AgentOrchestrator
    try:
        return AgentOrchestrator(project_root, pending_patch_path=path).preview_apply().diff_text
    except Exception:
        return None


def reject_pending(project_root: Path, *, session_id: str | None = None) -> str:
    """Reject the pending proposal without touching project files."""
    _patch_path(project_root, session_id).unlink(missing_ok=True)
    store = AgentSessionStore(project_root, session_id=session_id)
    state = store.load()
    if state is not None:
        store.save(state.model_copy(update={
            "pending_action": None,
            "status": "active",
            "last_observation": "Pending action rejected by user.",
        }))
    return "Rejected. No project files were modified."


def approve_pending_command(
    project_root: Path,
    action: dict[str, Any],
    *,
    session_id: str | None = None,
) -> str:
    from safecode.shell.runner import ShellRunner

    command = str(action.get("command", ""))
    if not command:
        return "Command approval failed: command is missing."
    result = ShellRunner(project_root).run(
        command,
        approved=True,
        timeout_seconds=int(action.get("timeout_seconds", 60)),
    )
    if not result.executed:
        return f"Command blocked by policy: {result.stderr or result.exit_code}"
    store = AgentSessionStore(project_root, session_id=session_id)
    state = store.load()
    if state is not None:
        store.save(state.model_copy(update={
            "pending_action": None,
            "status": "active",
            "last_observation": f"Approved command exited {result.exit_code}.",
        }))
    return f"Command finished with exit {result.exit_code}.\n{result.stdout}".rstrip()


def approve_pending_patch(project_root: Path, *, session_id: str | None = None) -> str:
    """Invoke the existing audited apply command after an explicit shell decision."""
    from safecode.agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(
        project_root,
        pending_patch_path=_patch_path(project_root, session_id),
    )
    preview = orchestrator.preview_apply()
    result = orchestrator.apply(preview.proposal)
    store = AgentSessionStore(project_root, session_id=session_id)
    state = store.load()
    if state is not None:
        store.save(state.model_copy(update={
            "pending_action": None,
            "status": "active",
            "last_observation": "Pending patch approved and applied by user.",
        }))
    files = ", ".join(result.files)
    return f"Approved and applied: {files}. Checkpoint: {result.checkpoint.checkpoint_id}."


def prompt_for_approval(
    project_root: Path,
    action: dict[str, Any],
    console: Any,
    *,
    session_id: str | None = None,
) -> str:
    """Show context and ask Approve / Reject / Explain until a decision is made."""
    preview = preview_pending_patch(project_root, session_id=session_id)
    if preview:
        from rich.syntax import Syntax
        console.print(Syntax(preview, "diff", theme="ansi_dark"))
    console.print(f"[yellow]{explain_pending(action)}[/yellow]")
    while True:
        try:
            choice = input("Approve, Reject, or Explain? [a/r/e]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "Approval deferred. Session preserved."
        if choice in {"a", "approve"}:
            if action.get("type") == "command":
                return approve_pending_command(project_root, action, session_id=session_id)
            if preview is None:
                return "This action cannot be approved inline yet. It remains pending."
            return approve_pending_patch(project_root, session_id=session_id)
        if choice in {"r", "reject"}:
            return reject_pending(project_root, session_id=session_id)
        if choice in {"e", "explain"}:
            console.print(explain_pending(action))
            continue
        console.print("Choose a, r, or e.")
