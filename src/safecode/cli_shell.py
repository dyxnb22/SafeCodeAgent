"""EXPERIMENTAL: sac shell — interactive AI shell for SafeCode Agent (v4.9+).

Start the AI shell from a project directory:

    cd myproject && sac shell

The shell provides a TTY REPL that routes natural-language questions to existing
SafeCode primitives (ask, edit, fix, run, status, apply, commit, debug, overview).
All mutation paths require explicit approval and delegate to the existing safe gates.

Slash commands: /status /task /overview /apply /commit /debug /help /exit

All surfaces in this module are EXPERIMENTAL and carry no stable contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json

_SHELL_BANNER = (
    "[bold]SafeCode Shell[/bold] [dim](EXPERIMENTAL v4.9)[/dim]\n"
    "Ask questions, use /help for slash commands, /exit to quit."
)

_SHELL_HELP = """\
Slash commands:
  /status   show current task, pending patch, and next step
  /task     show current task details
  /overview show project structure overview
  /apply    apply pending patch (requires confirmation)
  /commit   commit current task locally (requires confirmation)
  /debug    show last failure debug info
  /help     show this help
  /exit     exit the shell

Natural language input is routed by the intent router (v4.9.1+).
Mutation actions (apply, commit) always require explicit confirmation.
"""

_SHELL_PROMPT = "sac> "


def _read_line(*, is_tty: bool) -> str | None:
    """Read one line from the user. Returns None on EOF."""
    if is_tty:
        try:
            return input(_SHELL_PROMPT)
        except EOFError:
            return None
    else:
        line = sys.stdin.readline()
        if not line:
            return None
        return line.rstrip("\n")


def _slash_status(project_root: Path) -> str:
    """Return status text by calling the internal status builder."""
    try:
        from safecode.cli_status import _build_status_data
        from safecode.task.store import TaskStore
        store = TaskStore(project_root)
        data = _build_status_data(project_root, store)
        lines = [
            f"task_id: {data.get('task_id') or '(none)'}",
            f"goal: {data.get('goal') or '(none)'}",
            f"status: {data.get('status') or '(none)'}",
            f"pending_patch: {'yes' if data.get('pending_patch') else 'no'}",
            f"next_step: {data.get('next_step', '')}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Status unavailable: {exc}"


def _slash_task(project_root: Path) -> str:
    """Return current task details."""
    try:
        from safecode.task.store import TaskStore
        from safecode.context.redactor import redact_secrets
        store = TaskStore(project_root)
        current_id = store.current_id()
        if not current_id:
            return "No current task. Run: sac task new \"<goal>\""
        state = store.load(current_id)
        if state is None:
            return f"Task {current_id!r} not found."
        lines = [
            f"task_id: {state.task_id}",
            f"goal: {redact_secrets(state.goal)}",
            f"status: {state.status}",
            f"iterations: {len(state.iterations)}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Task info unavailable: {exc}"


def _slash_overview(project_root: Path) -> str:
    """Return a bounded project overview (implemented in v4.9.2)."""
    try:
        from safecode.shell_session.overview import build_project_overview
        ov = build_project_overview(project_root)
        return ov.render_text()
    except ImportError:
        return "Project overview available in v4.9.2."
    except Exception as exc:
        return f"Overview unavailable: {exc}"


def _slash_apply(project_root: Path, task_id: Optional[str], *, is_tty: bool) -> str:
    """Delegate to apply — requires explicit confirmation. Never auto-applies."""
    patch_path = project_root / ".sac" / "pending_patch.json"
    if not patch_path.exists():
        return "No pending patch found. Run: sac edit \"<change>\" first."

    if not is_tty:
        return "Cannot apply in non-TTY mode. Run: sac apply"

    try:
        confirm = input("Apply pending patch? This will modify files. [y/N]: ").strip().lower()
    except EOFError:
        return "Apply cancelled (no confirmation input)."

    if confirm not in ("y", "yes"):
        return "Apply cancelled."

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "safecode.cli", "apply"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return f"Apply succeeded.\n{output}"
    return f"Apply failed (exit {result.returncode}).\n{output}"


def _slash_commit(project_root: Path, task_id: Optional[str], *, is_tty: bool) -> str:
    """Delegate to commit — requires explicit confirmation. Never auto-commits."""
    if not is_tty:
        return "Cannot commit in non-TTY mode. Run: sac commit"

    try:
        confirm = input("Commit current task locally? [y/N]: ").strip().lower()
    except EOFError:
        return "Commit cancelled (no confirmation input)."

    if confirm not in ("y", "yes"):
        return "Commit cancelled."

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "safecode.cli", "commit"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return f"Commit succeeded.\n{output}"
    return f"Commit failed (exit {result.returncode}).\n{output}"


def _slash_debug(project_root: Path, task_id: Optional[str]) -> str:
    """Return last failure debug info."""
    try:
        from safecode.cli_debug import find_last_failure

        failure = find_last_failure(project_root, task_id=task_id)
        if failure is None:
            return "No recent failure found."
        data = failure.to_data()
        lines = [
            f"category: {data.get('category')}",
            f"message: {data.get('message')}",
            f"source: {data.get('source')}",
        ]
        suggested = data.get("suggested_next_command")
        if suggested:
            lines.append(f"suggested: {suggested}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Debug info unavailable: {exc}"


def _handle_slash_command(
    cmd: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> tuple[str, str, bool]:
    """Handle a slash command. Returns (response, intent, exit_shell)."""
    parts = cmd.split(None, 1)
    name = parts[0].lower()

    if name in ("/exit", "/quit"):
        return "Exiting shell.", "exit", True

    if name == "/help":
        return _SHELL_HELP, "help", False

    if name == "/status":
        return _slash_status(project_root), "status", False

    if name == "/task":
        return _slash_task(project_root), "task", False

    if name == "/overview":
        return _slash_overview(project_root), "overview", False

    if name == "/apply":
        return _slash_apply(project_root, task_id, is_tty=is_tty), "apply", False

    if name == "/commit":
        return _slash_commit(project_root, task_id, is_tty=is_tty), "commit", False

    if name == "/debug":
        return _slash_debug(project_root, task_id), "debug", False

    return f"Unknown slash command: {name!r}. Type /help for available commands.", "unknown_slash", False


def _handle_natural_language(
    user_input: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> tuple[str, str, bool]:
    """Route natural language input via the intent router (v4.9.1+).

    Returns (response, intent, exit_shell).
    """
    try:
        from safecode.shell_session.router import route_input
        return route_input(user_input, project_root, task_id, is_tty=is_tty)
    except ImportError:
        return (
            "Intent routing not available. Use /help for slash commands or run `sac ask` directly.",
            "ask_stub",
            False,
        )


def _process_input(
    user_input: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> tuple[str, str, bool]:
    """Dispatch one shell input. Returns (response, intent, exit_shell)."""
    if user_input.startswith("/"):
        return _handle_slash_command(user_input, project_root, task_id, is_tty=is_tty)
    return _handle_natural_language(user_input, project_root, task_id, is_tty=is_tty)


def _write_shell_audit_event(
    project_root: Path,
    session_id: str,
    turn_index: int,
    intent: str,
    task_id: Optional[str],
) -> None:
    """Write one audit event for a shell turn. Silently ignores failures."""
    try:
        from safecode.audit.logger import AuditLogger
        from safecode.audit.models import AuditEvent
        from safecode.utils.time import utc_now_iso

        event = AuditEvent(
            type="shell_turn",
            timestamp=utc_now_iso(),
            message=f"shell turn intent={intent}",
            metadata={
                "session_id": session_id,
                "turn_index": str(turn_index),
                "intent": intent,
            },
        )
        AuditLogger(project_root).write(event, task_id=task_id)
    except Exception:
        pass


def run_shell(
    project_root: Path,
    *,
    session_id: Optional[str] = None,
    is_tty: bool = True,
    json_output: bool = False,
) -> int:
    """Core shell loop. Returns exit code."""
    from safecode.shell_session.store import ShellSessionStore
    from safecode.shell_session.state import ShellTurn, _MAX_TURNS
    from safecode.task.store import TaskStore
    from safecode.utils.time import utc_now_iso

    store = ShellSessionStore(project_root)
    task_store = TaskStore(project_root)

    # Load or create session
    session = None
    if session_id:
        session = store.load(session_id)
    if session is None:
        current_task_id = task_store.current_id()
        session = store.create(task_id=current_task_id)

    if is_tty and not json_output:
        console.print(_SHELL_BANNER)

    while True:
        line = _read_line(is_tty=is_tty)
        if line is None:
            break

        user_input = line.strip()
        if not user_input:
            continue

        try:
            response, intent, exit_shell = _process_input(
                user_input, project_root, session.task_id, is_tty=is_tty
            )
        except KeyboardInterrupt:
            if is_tty:
                console.print("\n[yellow]Interrupted. Type /exit to quit.[/yellow]")
                continue
            break

        # Record turn (bounded)
        turn = ShellTurn(
            turn_index=session.next_turn_index(),
            user_input=user_input,
            shell_response=response,
            intent=intent,
            task_id=session.task_id,
        )
        all_turns = list(session.turns) + [turn]
        session = session.model_copy(update={
            "turns": all_turns[-_MAX_TURNS:],
            "updated_at": utc_now_iso(),
        })
        try:
            store.save(session)
        except Exception:
            pass

        # Audit event per turn
        _write_shell_audit_event(
            project_root,
            session.session_id,
            turn.turn_index,
            intent,
            session.task_id,
        )

        if json_output:
            print(render_json(CLIJSONResponse(
                command="shell turn",
                status="success",
                data={
                    "session_id": session.session_id,
                    "turn": turn.turn_index,
                    "intent": intent,
                    "response": response,
                },
            )))
        else:
            if is_tty:
                console.print(response)
            else:
                print(response)

        if exit_shell:
            break

    return 0


def register(app: typer.Typer) -> None:
    """Register sac shell on the given Typer app."""

    @app.command("shell")
    def shell_command(
        session: Optional[str] = typer.Option(None, "--session", help="Resume an existing session by ID."),
        json_output: bool = typer.Option(False, "--json", help="Output each turn as JSON (non-TTY friendly)."),
        non_tty: bool = typer.Option(False, "--non-tty", help="Force non-TTY (script/deterministic) mode."),
    ) -> None:
        """[EXPERIMENTAL] Start an interactive AI shell session.

        Ask natural-language questions, run /status, /apply, /debug, and more.
        All mutation paths require explicit approval. No auto-apply ever.
        """
        project_root = Path.cwd()
        is_tty = sys.stdin.isatty() and sys.stdout.isatty() and not non_tty
        code = run_shell(
            project_root,
            session_id=session,
            is_tty=is_tty,
            json_output=json_output,
        )
        raise typer.Exit(code=code)

    return shell_command
