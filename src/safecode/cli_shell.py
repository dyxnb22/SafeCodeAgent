"""EXPERIMENTAL: sac shell — interactive AI shell for SafeCode Agent (v4.9+).

Start the AI shell from a project directory:

    cd myproject && sac shell

The shell provides a TTY REPL that routes natural-language questions to existing
SafeCode primitives (ask, edit, fix, run, status, apply, commit, debug, overview).
All mutation paths require explicit approval and delegate to the existing safe gates.

Slash commands: /status /task /overview /model /apply /commit /debug /help /exit

All surfaces in this module are EXPERIMENTAL and carry no stable contract.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer

from safecode.agent.loop import AgentLoop
from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.context.redactor import redact_secrets

_SHELL_BANNER = (
    "[bold]SafeCode Shell[/bold] [dim](EXPERIMENTAL v4.17)[/dim]\n"
    "Ask questions, use /help for slash commands, /exit to quit."
)

_SHELL_HELP = """\
Slash commands:
  /status           show current task, pending patch, and next step
  /task             show current task details
  /overview         show project structure overview
  /model            show current model and available aliases
  /model <alias>    switch model: /model flash  /model pro  /model deepseek:pro
  /provider status  show current provider profile status
  /apply            apply pending patch (requires confirmation)
  /commit           commit current task locally (requires confirmation)
  /debug            show last failure debug info
  /clear            reset shell context and agent session history
  /undo             roll back the most recent write-tool checkpoint
  /history          show recent shell turns for the current session
  /tools            list available native tools (v4.20+)
  /cost             show session token and cost estimate (v5.2+)
  /help             show this help
  /exit             exit the shell

Model changes via /model are persisted globally (saved to user config).
Natural language input is routed by the intent router (v4.9.1+).
Mutation actions (apply, commit) always require explicit confirmation.
"""

_SHELL_PROMPT = "sac> "


def _shell_prompt(turn: int, cost_str: str = "") -> str:
    """Return shell prompt with turn counter and optional cost: sac[N · ~$0.03]>"""
    if cost_str:
        return f"sac[{turn} · {cost_str}]> "
    return f"sac[{turn}]> "

_SLASH_COMMANDS = [
    "/status", "/task", "/overview", "/model", "/provider",
    "/apply", "/commit", "/debug", "/clear", "/undo", "/history", "/tools",
    "/cost", "/help", "/exit", "/quit",
]


def _setup_readline() -> None:
    """Configure readline with history, tab completion, and dedup."""
    try:
        import atexit
        import readline
    except ImportError:
        return

    hist_dir = os.path.expanduser("~/.safecode")
    hist_file = os.path.join(hist_dir, "shell_history")
    try:
        os.makedirs(hist_dir, exist_ok=True)
    except OSError:
        return

    try:
        readline.read_history_file(hist_file)
    except (OSError, FileNotFoundError):
        pass

    try:
        readline.set_history_length(1000)
    except Exception:
        pass

    class SlashCompleter:
        def __init__(self, commands: list[str]) -> None:
            self.commands = commands

        def complete(self, text: str, state: int) -> str | None:
            if text.startswith("/"):
                matches = [c for c in self.commands if c.startswith(text)]
                if state < len(matches):
                    return matches[state]
            return None

    try:
        readline.set_completer(SlashCompleter(_SLASH_COMMANDS).complete)
        readline.parse_and_bind("tab: complete")
    except Exception:
        pass

    atexit.register(readline.write_history_file, hist_file)


def _maybe_render_markdown(response: str, *, is_tty: bool) -> None:
    """Render a shell response using Rich Markdown when it looks like formatted text.

    Only applies to TTY output. Falls back to plain console.print for non-TTY
    or when the response is a simple status line.
    """
    if not is_tty:
        print(response)
        return
    # Use Rich Markdown when response contains markdown-ish patterns
    if "```" in response or response.startswith("#") or "\n-" in response or "\n|" in response:
        from rich.markdown import Markdown
        console.print(Markdown(redact_secrets(response)))
    else:
        console.print(redact_secrets(response))


def _read_line(*, is_tty: bool, turn: int = 0) -> str | None:
    """Read one line from the user. Returns None on EOF.

    B11 fix: on EOF, prints '\n[exiting shell]' before returning None,
    consistent across TTY and non-TTY.
    """
    prompt = _shell_prompt(turn)  # sac[N]>
    if is_tty:
        try:
            return input(prompt)
        except EOFError:
            print("\n[exiting shell]")
            return None
    else:
        line = sys.stdin.readline()
        if not line:
            print("\n[exiting shell]")
            return None
        return line.rstrip("\n")


def _format_cost(tokens_in: int, tokens_out: int, cache_read: int = 0) -> str:
    """Format token counts as a compact display string for shell prompt or /cost."""
    # Rough pricing: input ~$3/Mtok, output ~$15/Mtok, cache read ~$0.30/Mtok
    cost_usd = (tokens_in / 1_000_000) * 3.0 + (tokens_out / 1_000_000) * 15.0 + (cache_read / 1_000_000) * 0.30
    if cost_usd >= 0.01:
        return f"~${cost_usd:.2f}"
    if cost_usd > 0:
        return f"~${cost_usd:.3f}"
    return ""


def _slash_cost(project_root: Path) -> str:
    """Return session cost estimate (v5.2.0)."""
    try:
        from safecode.config import SafeCodeConfig
        from safecode.llm.cost import SessionCostAccumulator

        config = SafeCodeConfig.load(project_root)
        sac_dir = project_root / config.sac_dir
        provider = config.llm.provider
        model = config.llm.model

        if provider == "mock":
            return "Session cost estimate\n─────────────────────\nProvider: mock (cost tracking disabled)"

        # Sum all known session cost files
        sessions_dir = sac_dir / "sessions"
        total_in = total_out = total_cache = 0
        if sessions_dir.exists():
            for cost_file in sessions_dir.glob("*/cost.json"):
                try:
                    session_id = cost_file.parent.name
                    usage = SessionCostAccumulator(sac_dir, session_id).load()
                    if usage:
                        total_in += usage.prompt_tokens
                        total_out += usage.completion_tokens
                        total_cache += usage.cache_read_tokens
                except Exception:
                    pass

        if total_in == 0 and total_out == 0:
            return "Session cost estimate\n─────────────────────\nNo token usage recorded yet."

        cost_str = _format_cost(total_in, total_out, total_cache)
        lines = [
            "Session cost estimate",
            "─────────────────────",
            f"Input tokens:   {total_in:>8,}",
            f"Output tokens:  {total_out:>8,}",
        ]
        if total_cache:
            lines.append(f"Cache reads:    {total_cache:>8,}   (cheaper rate)")
        if cost_str:
            lines.append(f"Estimated cost: {cost_str}")
        lines.append(f"Provider: {provider} · {model}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Cost estimate unavailable: {exc}"


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


def _slash_model(project_root: Path, args: str = "") -> str:
    """Show current model / aliases, or switch model via profile alias.

    Usage inside shell:
      /model            -> show current model and available aliases
      /model flash      -> switch to deepseek-v4-flash (persisted globally)
      /model pro        -> switch to deepseek-v4-pro (persisted globally)
      /model deepseek:flash
      /model <full-id> --provider <p> --api-key <k>  -> explicit form
    """
    try:
        import shlex

        from safecode.cli_model import (
            _render_model_list,
            _render_model_status,
            _switch_active_profile_model,
            write_user_model_config,
        )
        from safecode.config import SafeCodeConfig, _user_config_path

        path = _user_config_path()
        parts = shlex.split(args) if args.strip() else []

        if not parts:
            # Show status + available aliases
            status = _render_model_status(SafeCodeConfig.load(project_root), path)
            alias_list = _render_model_list(project_root, path)
            return status + "\n\n" + alias_list

        model = parts[0]

        # Parse optional flags
        provider = ""
        api_key = ""
        base_url = ""
        network = None
        index = 1
        while index < len(parts):
            item = parts[index]
            if item in ("--provider", "-p") and index + 1 < len(parts):
                provider = parts[index + 1]
                index += 2
                continue
            if item == "--api-key" and index + 1 < len(parts):
                api_key = parts[index + 1]
                index += 2
                continue
            if item == "--base-url" and index + 1 < len(parts):
                base_url = parts[index + 1]
                index += 2
                continue
            if item == "--network":
                network = True
                index += 1
                continue
            if item == "--no-network":
                network = False
                index += 1
                continue
            return f"Unknown /model option: {item!r}. Use /help."

        # Try alias resolution if no explicit provider/key flags
        if not provider and not api_key and not base_url:
            switched = _switch_active_profile_model(model, path)
            if switched is not None:
                sel_provider, resolved, sel_base_url, suggestion = switched
                hint = f"\n{suggestion}" if suggestion else ""
                written = write_user_model_config(
                    provider=sel_provider,
                    model=resolved,
                    base_url=sel_base_url or None,
                    api_key=None,
                    enable_user_network=network,
                )
                return (
                    f"Model config saved (globally): {written}\n"
                    f"Provider: {sel_provider}\n"
                    f"Model: {resolved} (from '{model}'){hint}"
                )

        # Explicit form: /model <name> --provider <p> ...
        current = SafeCodeConfig.load(project_root)
        selected_provider = provider or current.llm.provider
        written = write_user_model_config(
            provider=selected_provider,
            model=model,
            base_url=base_url or None,
            api_key=api_key or None,
            enable_user_network=network,
        )
        return (
            f"Model config saved (globally): {written}\n"
            f"Provider: {selected_provider}\n"
            f"Model: {model}\n"
            f"API key: {'configured' if api_key else 'unchanged'}"
        )
    except Exception as exc:
        return f"Model config failed: {exc}"


def _slash_provider_status(project_root: Path) -> str:
    """Return provider profile status for /provider status."""
    try:
        from safecode.llm.provider_profiles import (
            get_active_profile,
            get_active_profile_name,
            _PROVIDER_PRESETS,
        )
        from safecode.config import SafeCodeConfig, _read_toml, _user_config_path

        path = _user_config_path()
        active_name = get_active_profile_name(path)
        active_profile = get_active_profile(path)
        config = SafeCodeConfig.load(project_root)
        user_data = _read_toml(path)
        project_data = _read_toml(project_root / ".sac" / "config.toml")
        user_sandbox = user_data.get("sandbox", {}) if isinstance(user_data.get("sandbox", {}), dict) else {}
        project_sandbox = project_data.get("sandbox", {}) if isinstance(project_data.get("sandbox", {}), dict) else {}
        user_network_enabled = bool(user_sandbox.get("network_enabled", False))
        project_network_enabled = bool(project_sandbox.get("network_enabled", False))

        lines = ["Provider Status (EXPERIMENTAL)"]
        lines.append(f"  Active provider profile : {active_name or '(none)'}")
        lines.append(f"  Effective provider      : {config.llm.provider}")
        lines.append(f"  Effective model         : {config.llm.model}")

        if active_profile:
            source = active_profile.api_key_source()
            lines.append(f"  Credential source       : {source}")
            if active_profile.model_aliases:
                alias_str = ", ".join(
                    f"{k} -> {v}" for k, v in sorted(active_profile.model_aliases.items())
                )
                lines.append(f"  Model aliases           : {alias_str}")
        else:
            lines.append("  Credential source       : (no profile configured)")

        lines.append(f"  User network enabled    : {user_network_enabled}")
        lines.append(f"  Project network enabled : {project_network_enabled}")
        lines.append(f"  Effective network       : {config.sandbox.network_enabled}")

        if active_name is None:
            lines.append("")
            lines.append("-> Run: sac provider add deepseek")
        elif active_profile and active_profile.api_key_source() == "missing":
            preset = _PROVIDER_PRESETS.get(active_name, {})
            env_var = preset.get("api_key_env", "")
            if env_var:
                lines.append(f"-> Set {env_var} or run: sac provider add {active_name} --api-key <key>")
        if active_name and not user_network_enabled:
            lines.append(f"-> Enable user network: sac provider add {active_name} --yes")
        if active_name and not project_network_enabled:
            lines.append("-> Enable project network: sac setup --yes --network")

        return "\n".join(lines)
    except Exception as exc:
        return f"Provider status unavailable: {exc}"


def _slash_apply(project_root: Path, task_id: Optional[str], *, is_tty: bool) -> str:
    """Delegate to apply — shows diff inline, requires confirmation. Never auto-applies."""
    patch_path = project_root / ".sac" / "pending_patch.json"
    if not patch_path.exists():
        return "No pending patch found. Run: sac edit \"<change>\" first."

    if not is_tty:
        return "Cannot apply in non-TTY mode. Run: sac apply"

    # Show diff preview inline before asking for confirmation
    try:
        from safecode.agent.orchestrator import AgentOrchestrator
        from rich.syntax import Syntax
        preview = AgentOrchestrator(project_root).preview_apply()
        console.print(Syntax(preview.diff_text, "diff", theme="ansi_dark"))
    except Exception as exc:
        return f"Cannot preview patch: {exc}"

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

    if name == "/cost":
        return _slash_cost(project_root), "cost", False

    if name == "/task":
        return _slash_task(project_root), "task", False

    if name == "/overview":
        return _slash_overview(project_root), "overview", False

    if name == "/model":
        return _slash_model(project_root, parts[1] if len(parts) > 1 else ""), "model", False

    if name == "/provider":
        sub = (parts[1] if len(parts) > 1 else "").strip().lower()
        if sub == "status":
            return _slash_provider_status(project_root), "provider_status", False
        return (
            "Usage: /provider status",
            "provider_unknown",
            False,
        )

    if name == "/clear":
        # B10 fix: actually clear the AgentSessionStore so context is reset.
        try:
            from safecode.agent.session import AgentSessionStore
            AgentSessionStore(project_root).clear()
        except Exception:
            pass
        return "Shell context cleared. Start a new conversation.", "clear", False

    if name == "/undo":
        # Roll back the most recent write-tool checkpoint.
        try:
            from safecode.checkpoint.manager import CheckpointManager
            meta = CheckpointManager(project_root).rollback_last()
            paths = [op.path for op in meta.file_operations]
            return f"Rolled back checkpoint {meta.checkpoint_id}\nRestored: {', '.join(paths)}", "undo", False
        except FileNotFoundError:
            return "No checkpoint to roll back.", "undo", False
        except Exception as exc:
            return f"Rollback failed: {exc}", "undo", False

    if name == "/history":
        # Show current session's turns in a compact table.
        from safecode.shell_session.store import ShellSessionStore
        try:
            store = ShellSessionStore(project_root)
            session_ids = store.list_sessions()
            if not session_ids:
                return "No shell session history.", "history", False
            latest_id = session_ids[-1]
            latest = store.load(latest_id)
            if latest is None:
                return "No shell session history.", "history", False
            lines = [f"Session {latest.session_id} — {len(latest.turns)} turns"]
            for t in latest.turns[-10:]:
                lines.append(f"  [{t.turn_index}] {t.user_input[:60]!r}")
            return "\n".join(lines), "history", False
        except Exception as exc:
            return f"History unavailable: {exc}", "history", False

    if name == "/tools":
        # List available native tools (from the NativeToolDispatcher if wired).
        lines = ["Available native tools (v4.20+, EXPERIMENTAL):"]
        from safecode.agent.read_tools import READ_FILE_SPEC, LIST_FILES_SPEC, SEARCH_FILES_SPEC, GREP_FILES_SPEC
        from safecode.agent.write_tools import EDIT_FILE_SPEC, WRITE_FILE_SPEC
        from safecode.agent.command_tool import RUN_COMMAND_SPEC
        for spec in sorted([READ_FILE_SPEC, LIST_FILES_SPEC, SEARCH_FILES_SPEC, GREP_FILES_SPEC,
                             EDIT_FILE_SPEC, WRITE_FILE_SPEC, RUN_COMMAND_SPEC], key=lambda s: s.name):
            approval = " [requires approval]" if spec.requires_approval else ""
            lines.append(f"  {spec.name}{approval}: {spec.description[:80]}")
        return "\n".join(lines), "tools", False

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
        _setup_readline()

    turn_count = 0
    while True:
        line = _read_line(is_tty=is_tty, turn=turn_count)
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
            _maybe_render_markdown(response, is_tty=is_tty)

        turn_count += 1

        if exit_shell:
            break

    return 0


def _run_agentic_shell(
    project_root: Path,
    *,
    is_tty: bool = True,
    json_output: bool = False,
    auto_edit: bool = False,
    full_auto: bool = False,
    command_delay_ms: int = 500,
) -> int:
    """[EXPERIMENTAL] Drive AgentLoop.run() from a single user input line.

    Reads one line of user input as the goal, runs the AgentLoop, and renders
    the result. Uses Rich Status panel for real-time step progress in TTY mode.

    With --auto-edit, edit_file and write_file execute without prompting.
    With --full-auto, run_command also executes (policy gates still apply).
    run_command and GitHub write tools always require approval in plain agentic mode.
    """
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    from safecode.agent.step_model import APPROVAL_REQUIRED_KINDS

    if full_auto:
        mode_label = "full-auto"
    elif auto_edit:
        mode_label = "auto-edit"
    else:
        mode_label = "v4.18"

    if is_tty:
        console.print(f"[bold]SafeCode Shell[/bold] [dim](EXPERIMENTAL --agentic mode {mode_label})[/dim]")
        if full_auto:
            console.print(
                "[yellow]Full-auto mode: edit_file/write_file/run_command execute automatically. "
                f"Command grace period: {command_delay_ms}ms (Ctrl-C to abort). "
                "High-risk commands still blocked. Use sac rollback --last to undo.[/yellow]"
            )
        elif auto_edit:
            console.print(
                "[yellow]Auto-edit mode: edit_file/write_file execute without prompting. "
                "Use sac rollback --last to undo.[/yellow]"
            )
        console.print("Enter your goal (one line), or Ctrl-C to exit.")

    line = _read_line(is_tty=is_tty)
    if line is None or not line.strip():
        if is_tty:
            console.print("[yellow]No input received. Exiting.[/yellow]")
        return 0

    goal = line.strip()
    loop = AgentLoop(
        project_root,
        auto_edit=auto_edit,
        full_auto=full_auto,
        command_delay_ms=command_delay_ms,
    )

    step_updates: list[str] = []
    files_edited: list[str] = []

    def on_step(result):
        obs = result.observation[:120]
        step_updates.append(obs)
        # Track auto-edited files for session summary.
        if auto_edit and result.state.pending_action:
            action = result.state.pending_action
            if action.get("type") == "native_turn":
                write_calls = int(action.get("write_calls", "0") or "0")
                if write_calls:
                    files_edited.append(f"+{write_calls} files (step {len(step_updates)})")
            if is_tty and not json_output:
                write_calls = int(action.get("write_calls", "0") or "0") if action.get("type") == "native_turn" else 0
                if write_calls:
                    console.print(f"  [green]✓[/green] {write_calls} file(s) edited")

    try:
        if is_tty and not json_output:
            from rich.status import Status
            with Status("[bold blue]Agent loop running...", spinner="dots"):
                result = loop.run(goal, max_steps=8, on_step=on_step)
        else:
            result = loop.run(goal, max_steps=8, on_step=on_step)
    except (FileNotFoundError, ValueError) as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="shell --agentic", status="error", error=str(exc))))
        else:
            console.print(f"[red]{exc}[/red]")
        return 1

    last_typed = loop.last_typed_result

    if json_output:
        status = result.stopped_reason if result.stopped_reason in ("completed", "approval_required") else "stopped"
        data: dict = {
            "session_id": result.state.session_id,
            "stopped_reason": result.stopped_reason,
            "steps_count": len(result.steps),
            "status": result.state.status,
            "step_updates": step_updates,
            "auto_edit": auto_edit,
            "full_auto": full_auto,
        }
        if files_edited:
            data["files_edited_summary"] = files_edited
        if last_typed is not None:
            data["last_typed_result"] = last_typed.model_dump()
        session_cost_json = loop.session_cost()
        if session_cost_json:
            data["cost"] = {
                "input_tokens": session_cost_json.prompt_tokens,
                "output_tokens": session_cost_json.completion_tokens,
                "cache_read_tokens": session_cost_json.cache_read_tokens,
                "estimated_usd": round(
                    (session_cost_json.prompt_tokens / 1_000_000) * 3.0
                    + (session_cost_json.completion_tokens / 1_000_000) * 15.0
                    + (session_cost_json.cache_read_tokens / 1_000_000) * 0.30,
                    4,
                ),
            }
        print(render_json(CLIJSONResponse(command="shell --agentic", status=status, data=data)))
        return 0

    for index, step_result in enumerate(result.steps, start=1):
        line_out = f"Step {index}: {step_result.observation}"
        if is_tty:
            console.print(line_out)
        else:
            print(line_out)

    # Session summary (v5.1.0+: always show in auto-edit/full-auto mode)
    # v5.2.0: include cost estimate
    summary_parts = [
        f"Session: {result.state.session_id}",
        f"Status: {result.state.status}",
        f"Stopped: {result.stopped_reason}",
    ]
    if (auto_edit or full_auto) and loop._native_write_count:
        summary_parts.append(f"Files edited: {loop._native_write_count}")
        summary_parts.append(f"Undo all: sac rollback --session {result.state.session_id}")

    session_cost = loop.session_cost()
    if session_cost and (session_cost.prompt_tokens or session_cost.completion_tokens):
        cost_str = _format_cost(session_cost.prompt_tokens, session_cost.completion_tokens, session_cost.cache_read_tokens)
        tokens_k_in = session_cost.prompt_tokens // 1000
        tokens_k_out = session_cost.completion_tokens // 1000
        cost_display = f"Cost: {cost_str} ({tokens_k_in}k in / {tokens_k_out}k out)" if cost_str else f"Tokens: {tokens_k_in}k in / {tokens_k_out}k out"
        summary_parts.append(cost_display)

    summary = " | ".join(summary_parts)
    if is_tty:
        console.print(f"[dim]{summary}[/dim]")
    else:
        print(summary)

    return 0


def register(app: typer.Typer) -> None:
    """Register sac shell on the given Typer app."""

    @app.command("shell", hidden=True)
    def shell_command(
        session: Optional[str] = typer.Option(None, "--session", help="Resume an existing session by ID."),
        model: str = typer.Option("", "--model", help="One-shot model override for this shell session (e.g. pro or deepseek:pro)."),
        json_output: bool = typer.Option(False, "--json", help="Output each turn as JSON (non-TTY friendly)."),
        non_tty: bool = typer.Option(False, "--non-tty", help="Force non-TTY (script/deterministic) mode."),
        agentic: bool = typer.Option(
            False,
            "--agentic",
            help="[EXPERIMENTAL] Route user input directly to AgentLoop.run() instead of the intent router.",
        ),
        auto_edit: bool = typer.Option(
            False,
            "--auto-edit",
            help="[EXPERIMENTAL] Auto-approve edit_file/write_file in --agentic mode. "
                 "run_command and GitHub write tools still require approval. "
                 "Checkpoints are always created. Implies --agentic.",
        ),
        full_auto: bool = typer.Option(
            False,
            "--full-auto",
            help="[EXPERIMENTAL] Auto-approve edit_file, write_file, AND run_command "
                 "(within existing shell policy). High-risk commands still blocked. "
                 "GitHub write tools still prompt. Cannot be persisted. Implies --agentic.",
        ),
        command_delay_ms: int = typer.Option(
            500,
            "--command-delay-ms",
            help="[EXPERIMENTAL] Grace period (ms) before run_command executes in --full-auto mode. "
                 "Press Ctrl-C during delay to abort. Range: 0–2000. Default: 500.",
        ),
    ) -> None:
        """[EXPERIMENTAL] Start an interactive AI shell session.

        Ask natural-language questions, run /status, /apply, /debug, and more.
        All mutation paths require explicit approval. No auto-apply ever.

        With --agentic, user input becomes the goal for an AgentLoop.run() invocation
        (the same loop sac agent run drives). Existing shell behavior is unchanged
        without --agentic.

        With --auto-edit (implies --agentic), edit_file and write_file execute
        without per-call prompts. Use 'sac rollback --last' or '/undo' to undo.

        With --full-auto (implies --agentic), run_command also executes automatically
        within policy limits. A preview line is printed and a grace period allows
        Ctrl-C abort. High-risk commands are still blocked. Cannot be persisted.
        """
        project_root = Path.cwd()
        is_tty = sys.stdin.isatty() and sys.stdout.isatty() and not non_tty
        delay_ms = max(0, min(2000, command_delay_ms))
        if model:
            from safecode.cli_model import apply_model_override_env
            try:
                _provider, resolved, suggestion = apply_model_override_env(model)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc
            if is_tty and not json_output:
                if suggestion:
                    console.print(f"[yellow]{suggestion}[/yellow]")
                console.print(f"[dim]Session model override: {resolved}[/dim]")

        if full_auto or auto_edit or agentic:
            code = _run_agentic_shell(
                project_root,
                is_tty=is_tty,
                json_output=json_output,
                auto_edit=auto_edit,
                full_auto=full_auto,
                command_delay_ms=delay_ms,
            )
        else:
            code = run_shell(
                project_root,
                session_id=session,
                is_tty=is_tty,
                json_output=json_output,
            )
        raise typer.Exit(code=code)

    return shell_command
