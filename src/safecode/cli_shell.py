"""EXPERIMENTAL: sac shell — interactive AI shell for SafeCode Agent (v4.9+).

Start the AI shell from a project directory:

    cd myproject && sac shell

The shell provides a TTY REPL that routes natural-language questions to existing
SafeCode primitives (ask, edit, fix, run, status, apply, commit, debug, overview).
All mutation paths require explicit approval and delegate to the existing safe gates.

Slash commands: /status /continue /memory /ready /task /overview /model /apply /commit /help /exit

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
    "Type a request, or use /status for the workspace dashboard. /help lists commands."
)

_SHELL_HELP = """\
Slash commands
==============

Start here:
  /status           workspace dashboard and next safe step
  /continue         take one safe step, or explain the blocker

Work:
  Type a request    ask, inspect, edit, or fix using natural language
  /apply            apply pending patch (shows diff and asks first)
  /commit           commit current task locally (asks first)
  /undo             roll back the most recent write-tool checkpoint

Inspect:
  /task             show current task card
  /timeline         show latest high-signal agent timeline
  /sessions         show recent shell and agent sessions
  /history          show recent shell turns
  /debug            show last failure debug info

Configure:
  /ready            check provider/model/network/memory readiness
  /ready --live     opt-in live provider smoke
  /model            show current model, aliases, and readiness
  /model <alias>    switch model: /model flash  /model pro
  /provider status  show provider profile status

Memory:
  /memory           show what will enter context
  /memory review    review pending learned facts
  /memory teach <text>
                    add a non-secret project note
  /memory prune     remove stale workspace memory

Advanced:
  /demo             show a safe first-run demo path
  /smoke live       run the live-provider smoke (opt-in network)
  /tools            list native tools and approval flags
  /cost             show session token/cost estimate
  /mode plan|build  switch agentic shell mode
  /clear            reset shell context and agent session history
  /exit             exit the shell

Model changes via /model are persisted globally (saved to user config).
Natural language input is routed by the intent router (v4.9.1+).
Mutation actions (apply, commit) always require explicit confirmation.
"""

_SHELL_PROMPT = "sac> "


def _shell_prompt(turn: int, cost_str: str = "", task_str: str = "") -> str:
    """Return shell prompt with turn counter, optional cost, optional task status (v5.2.1)."""
    parts = [str(turn)]
    if task_str:
        parts.append(task_str)
    if cost_str:
        parts.append(cost_str)
    inner = " · ".join(parts)
    return f"sac[{inner}]> "

_SLASH_COMMANDS = [
    "/status", "/continue", "/timeline", "/sessions", "/resume", "/task", "/overview", "/model", "/provider",
    "/memory", "/ready", "/doctor", "/demo", "/smoke",
    "/apply", "/commit", "/debug", "/clear", "/undo", "/history", "/tools",
    "/cost", "/mode", "/help", "/exit", "/quit",
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


def _read_line(*, is_tty: bool, turn: int = 0, prompt_override: str | None = None) -> str | None:
    """Read one line from the user. Returns None on EOF.

    EOF prints '\n[exiting shell]' consistently across TTY and non-TTY.
    Callers may pass a pre-formatted prompt string via prompt_override.
    """
    prompt = prompt_override if prompt_override is not None else _shell_prompt(turn)
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


def _slash_budget(project_root: Path) -> str:
    """Show session token usage, estimated cost, and cap (v5.8.0)."""
    try:
        from safecode.config import SafeCodeConfig
        from safecode.llm.cost import SessionCostAccumulator, render_budget_summary

        config = SafeCodeConfig.load(project_root)
        sac_dir = project_root / config.sac_dir
        cap = config.cost.max_tokens_per_session

        # Sum all known session cost files
        sessions_dir = sac_dir / "sessions"
        from safecode.llm.cost import TokenUsage
        total = TokenUsage()
        if sessions_dir.exists():
            for cost_file in sessions_dir.glob("*/cost.json"):
                try:
                    usage = SessionCostAccumulator(sac_dir, cost_file.parent.name).load()
                    if usage:
                        total = total + usage
                except Exception:
                    pass

        summary = render_budget_summary(total, cap)
        if cap is not None:
            pct = total.total_tokens / cap * 100 if cap > 0 else 0
            if pct >= 90:
                summary += "\n⚠  Budget warning: 90%+ used."
        return summary
    except Exception as exc:
        return f"Budget info unavailable: {exc}"


def _session_edit_summary(project_root: Path, session_id: str) -> str:
    """Render a file-tree-style summary of edits from the session journal (v5.2.1)."""
    try:
        from safecode.state.journal import AgentJournalStore
        events = AgentJournalStore(project_root).read(session_id)
    except Exception:
        return ""

    # Collect file paths and operations from journal events
    edits: dict[str, list[str]] = {}  # path → list of operations
    for event in events:
        if event.type not in ("action", "typed_result"):
            continue
        payload = event.payload or {}
        pending = payload.get("pending_action") or {}
        if isinstance(pending, dict):
            tool = pending.get("tool_name", "")
            if tool in ("edit_file", "write_file"):
                path = str(pending.get("intent_fields", {}).get("path", "") or "")
                op = "edited" if tool == "edit_file" else "created/overwritten"
                if path:
                    edits.setdefault(path, []).append(op)

    if not edits:
        return ""

    # Build file-tree style output
    root = project_root.resolve()
    tree: dict[str, list[tuple[str, str]]] = {}  # dir → list of (filename, op)
    for path_str, ops in edits.items():
        p = (root / path_str).resolve()
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        parts = rel.parts
        if len(parts) >= 2:
            directory = str(Path(*parts[:-1])) + "/"
            filename = parts[-1]
        else:
            directory = "./"
            filename = str(rel)
        tree.setdefault(directory, []).append((filename, ops[-1]))

    if not tree:
        return ""

    lines = ["Files changed this session"]
    dirs = sorted(tree.keys())
    for i, directory in enumerate(dirs):
        is_last_dir = i == len(dirs) - 1
        dir_prefix = "└── " if is_last_dir else "├── "
        lines.append(f"{dir_prefix}{directory}")
        files = tree[directory]
        for j, (filename, op) in enumerate(sorted(files)):
            is_last_file = j == len(files) - 1
            file_prefix = "    └── " if is_last_dir else "│   └── " if is_last_file else "│   ├── "
            lines.append(f"{file_prefix}{filename}   {op}")

    return "\n".join(lines)


def _git_state(project_root: Path) -> tuple[str, bool | None]:
    """Return (branch, dirty) without raising."""
    import subprocess

    branch = "(unknown)"
    dirty: bool | None = None
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            branch = value
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            dirty = bool(result.stdout.strip())
    except Exception:
        pass
    return branch, dirty


def _build_shell_status_data(project_root: Path) -> dict[str, object]:
    """Build the in-shell dashboard payload without mutating project state."""
    from safecode.agent.session import AgentSessionStore
    from safecode.config import SafeCodeConfig, _read_toml, _user_config_path
    from safecode.llm.provider_profiles import get_active_profile, get_active_profile_name
    from safecode.memory.facade import MemoryFacade
    from safecode.memory.facts import ProjectFactStore
    from safecode.memory.session_store import SessionSummaryStore
    from safecode.task.store import TaskStore
    from safecode.cli_status import _build_status_data

    config = SafeCodeConfig.load(project_root)
    user_data = _read_toml(_user_config_path())
    user_sandbox = user_data.get("sandbox", {}) if isinstance(user_data.get("sandbox", {}), dict) else {}

    active_name = get_active_profile_name()
    active_profile = get_active_profile()
    credential_source = active_profile.api_key_source() if active_profile is not None else (
        "mock" if config.llm.provider == "mock" else ("user-config [llm]" if config.llm.api_key else "missing")
    )

    task_data = _build_status_data(project_root, TaskStore(project_root))
    agent = AgentSessionStore(project_root).load()
    memory = MemoryFacade(project_root)
    fact_store = ProjectFactStore(project_root / ".sac")
    branch, dirty = _git_state(project_root)

    pending_facts = len(fact_store.list_facts(status="pending"))
    approved_facts = len(fact_store.list_facts(status="approved"))
    recent_summaries = len(SessionSummaryStore(project_root / ".sac").load_recent(limit=3))
    project_notes = memory.read_project_notes()
    pinned = memory.read_pinned_files()

    next_actions: list[str] = []
    task_next = str(task_data.get("next_step") or "")
    if task_next:
        next_actions.append(task_next.replace("Run: ", ""))
    if active_name is None and config.llm.provider != "mock":
        next_actions.append("sac provider add deepseek --store keychain")
    elif config.llm.provider != "mock" and credential_source == "missing":
        next_actions.append(f"sac provider add {active_name or config.llm.provider} --store keychain")
    if config.llm.provider != "mock" and not config.sandbox.network_enabled:
        next_actions.append("sac setup --yes --network")
    if pending_facts:
        next_actions.append("sac memory list-facts --pending")
    if agent is not None and agent.status in {"waiting_for_user", "active", "aborted"}:
        next_actions.append(f"/timeline {agent.session_id}")

    if not next_actions:
        next_actions.append('Type a request, or run /overview to inspect the project.')

    return {
        "provider": {
            "effective_provider": config.llm.provider,
            "model": config.llm.model,
            "active_profile": active_name,
            "credential_source": credential_source,
            "base_url": config.llm.base_url,
        },
        "task": task_data,
        "agent_session": {
            "session_id": agent.session_id if agent else None,
            "goal": agent.goal if agent else None,
            "status": agent.status if agent else None,
            "current_step": agent.current_step if agent else None,
            "plan_steps": len(agent.plan) if agent else 0,
        },
        "memory": {
            "approved_facts": approved_facts,
            "pending_facts": pending_facts,
            "recent_summaries": recent_summaries,
            "project_notes": bool(project_notes.strip()),
            "pinned_files": len(pinned),
        },
        "safety": {
            "policy": config.policy,
            "effective_network": config.sandbox.network_enabled,
            "user_network": bool(user_sandbox.get("network_enabled", False)),
            "allowlist": list(config.sandbox.network_allowlist),
        },
        "workspace": {
            "branch": branch,
            "dirty": dirty,
        },
        "next_actions": next_actions[:5],
    }


def _render_shell_status(data: dict[str, object]) -> str:
    """Render the in-shell dashboard as compact plain text/Markdown."""
    provider = data["provider"] if isinstance(data.get("provider"), dict) else {}
    task = data["task"] if isinstance(data.get("task"), dict) else {}
    agent = data["agent_session"] if isinstance(data.get("agent_session"), dict) else {}
    memory = data["memory"] if isinstance(data.get("memory"), dict) else {}
    safety = data["safety"] if isinstance(data.get("safety"), dict) else {}
    workspace = data["workspace"] if isinstance(data.get("workspace"), dict) else {}
    next_actions = data.get("next_actions") if isinstance(data.get("next_actions"), list) else []

    dirty = workspace.get("dirty")
    dirty_label = "dirty" if dirty is True else ("clean" if dirty is False else "unknown")
    network_label = "on" if safety.get("effective_network") else "off"
    allowlist = safety.get("allowlist") or []
    allowlist_label = ", ".join(str(item) for item in allowlist[:3]) if allowlist else "[]"
    if len(allowlist) > 3:
        allowlist_label += f", +{len(allowlist) - 3}"

    lines = [
        "# SafeCode Status",
        "",
        "Provider",
        f"- effective: {provider.get('effective_provider', '(unknown)')} / {provider.get('model', '(unknown)')}",
        f"- profile: {provider.get('active_profile') or '(none)'}",
        f"- credential: {provider.get('credential_source', 'missing')}",
        "",
        "Task",
        f"- task_id: {task.get('task_id') or '(none)'}",
        f"- status: {task.get('status') or '(none)'}",
        f"- pending patch: {'yes' if task.get('pending_patch') else 'no'}",
    ]
    if task.get("goal"):
        lines.append(f"- goal: {str(task.get('goal'))[:120]}")
    if task.get("last_test_command"):
        lines.append(f"- last test: {task.get('last_test_command')} (exit {task.get('last_test_exit_code')})")

    lines.extend([
        "",
        "Session",
        f"- agent: {agent.get('session_id') or '(none)'}",
        f"- state: {agent.get('status') or '(none)'}",
    ])
    if agent.get("session_id"):
        lines.append(f"- step: {agent.get('current_step')}/{agent.get('plan_steps')}")

    lines.extend([
        "",
        "Memory",
        f"- approved facts: {memory.get('approved_facts', 0)}",
        f"- pending facts: {memory.get('pending_facts', 0)}",
        f"- recent summaries: {memory.get('recent_summaries', 0)}",
        f"- project notes: {'yes' if memory.get('project_notes') else 'no'}",
        f"- pinned files: {memory.get('pinned_files', 0)}",
        "",
        "Safety",
        f"- policy: {safety.get('policy', '(unknown)')}",
        f"- network: {network_label}",
        f"- allowlist: {allowlist_label}",
        "",
        "Workspace",
        f"- branch: {workspace.get('branch', '(unknown)')}",
        f"- tree: {dirty_label}",
        "",
        "Next",
    ])
    for item in next_actions:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _slash_status(project_root: Path) -> str:
    """Return the in-shell status dashboard."""
    try:
        return _render_shell_status(_build_shell_status_data(project_root))
    except Exception as exc:
        return f"Status unavailable: {exc}"


def _format_card(title: str, rows: list[tuple[str, str]], *, next_step: str = "", details: list[str] | None = None) -> str:
    """Render a compact product-style card."""
    lines = [title, "-" * len(title)]
    for label, value in rows:
        lines.append(f"{label}: {value}")
    if details:
        lines.append("")
        lines.append("Details:")
        lines.extend(f"- {item}" for item in details)
    if next_step:
        lines.append("")
        lines.append(f"Next: {next_step}")
    return "\n".join(lines)


def _slash_continue(project_root: Path) -> str:
    """Take the next safe step, or explain the blocker without crossing approval gates."""
    try:
        data = _build_shell_status_data(project_root)
        provider = data["provider"] if isinstance(data.get("provider"), dict) else {}
        task = data["task"] if isinstance(data.get("task"), dict) else {}
        agent = data["agent_session"] if isinstance(data.get("agent_session"), dict) else {}
        safety = data["safety"] if isinstance(data.get("safety"), dict) else {}

        effective_provider = str(provider.get("effective_provider") or "mock")
        credential = str(provider.get("credential_source") or "missing")
        if effective_provider != "mock" and credential == "missing":
            profile = provider.get("active_profile") or effective_provider
            return _format_card(
                "Blocked: Provider credential missing",
                [
                    ("Provider", effective_provider),
                    ("Credential", "missing"),
                    ("Model", str(provider.get("model") or "(unknown)")),
                ],
                next_step=f"sac provider add {profile} --store keychain",
                details=["SafeCode checks env vars, provider keychain, generic env vars, then user config."],
            )

        if effective_provider != "mock" and not safety.get("effective_network"):
            return _format_card(
                "Blocked: Provider network disabled",
                [
                    ("Provider", effective_provider),
                    ("Network", "off"),
                ],
                next_step="sac setup --yes --network",
            )

        if task.get("pending_patch"):
            return _format_card(
                "Pending patch is ready",
                [
                    ("Pending patch", "yes"),
                    ("Task", str(task.get("task_id") or "(none)")),
                ],
                next_step="/apply",
                details=["SafeCode will show the diff and ask before modifying files."],
            )

        agent_id = agent.get("session_id")
        agent_status = str(agent.get("status") or "")
        if agent_id and agent_status == "waiting_for_user":
            return _format_card(
                "Blocked: Agent is waiting for you",
                [
                    ("Session", str(agent_id)),
                    ("State", agent_status),
                ],
                next_step=f"/timeline {agent_id}",
                details=["Answer the prompt, adjust the task, or use /apply if a patch is pending."],
            )
        if agent_id and agent_status == "aborted":
            return _format_card(
                "Blocked: Agent session aborted",
                [
                    ("Session", str(agent_id)),
                    ("State", agent_status),
                ],
                next_step=f"/resume {agent_id}",
            )
        if agent_id and agent_status in {"active", ""}:
            from safecode.agent.loop import AgentLoop

            result = AgentLoop(project_root).run(None, max_steps=1)
            observation = result.steps[-1].observation if result.steps else result.state.last_observation
            lines = [
                "Continued one safe agent step.",
                f"session: {result.state.session_id}",
                f"status: {result.state.status}",
                f"step: {result.state.current_step}/{len(result.state.plan)}",
                f"stopped_reason: {result.stopped_reason}",
            ]
            if observation:
                lines.append(f"observation: {' '.join(observation.split())[:240]}")
            lines.append("Next: /status")
            return "\n".join(lines)

        next_step = str(task.get("next_step") or "")
        if next_step:
            return _format_card(
                "No active agent session",
                [("Task", str(task.get("task_id") or "(none)"))],
                next_step=next_step,
            )
        return _format_card(
            "Nothing To Continue",
            [("Task", "(none)"), ("Agent session", "(none)")],
            next_step='Type a request, or run /overview to inspect the project.',
        )
    except Exception as exc:
        return f"Continue unavailable: {exc}"


def _slash_ready(project_root: Path, args: str = "") -> str:
    """Return a readiness card; with --live, run the opt-in live smoke."""
    args = args.strip()
    if "--live" in args:
        return _slash_smoke(project_root, "live")
    try:
        data = _build_shell_status_data(project_root)
        provider = data["provider"] if isinstance(data.get("provider"), dict) else {}
        safety = data["safety"] if isinstance(data.get("safety"), dict) else {}
        memory = data["memory"] if isinstance(data.get("memory"), dict) else {}
        effective_provider = str(provider.get("effective_provider") or "mock")
        credential = str(provider.get("credential_source") or "missing")
        network_ok = effective_provider == "mock" or bool(safety.get("effective_network"))
        credential_ok = effective_provider == "mock" or credential != "missing"
        verdict = "READY" if credential_ok and network_ok else "NEEDS_SETUP"
        details: list[str] = []
        next_step = "/status"
        if not credential_ok:
            profile = provider.get("active_profile") or effective_provider
            details.append("Credential is missing.")
            next_step = f"sac provider add {profile} --store keychain"
        if not network_ok:
            details.append("Network is disabled for the active real provider.")
            next_step = "sac setup --yes --network"
        if int(memory.get("pending_facts", 0) or 0):
            details.append("Pending memory facts are waiting for review.")
        return _format_card(
            f"Readiness: {verdict}",
            [
                ("Provider", f"{effective_provider} / {provider.get('model', '(unknown)')}"),
                ("Credential", credential),
                ("Network", "ok" if network_ok else "blocked"),
                ("Policy", str(safety.get("policy") or "(unknown)")),
                ("Memory", f"{memory.get('approved_facts', 0)} approved, {memory.get('pending_facts', 0)} pending"),
            ],
            next_step=next_step,
            details=details or ["Use /ready --live for an opt-in provider smoke."],
        )
    except Exception as exc:
        return f"Ready check unavailable: {exc}"


def _slash_memory(project_root: Path, args: str = "") -> str:
    """In-shell memory UX: explain, review, teach, approve/reject, prune."""
    try:
        import shlex

        from safecode.memory.facade import MemoryFacade
        from safecode.memory.facts import ProjectFactStore
        from safecode.memory.session_store import SessionSummaryStore
        from safecode.memory.workspace_memory import WorkspaceMemoryStore

        parts = shlex.split(args) if args.strip() else []
        action = parts[0].lower() if parts else "show"
        rest = parts[1:]
        sac_dir = project_root / ".sac"
        facts = ProjectFactStore(sac_dir)
        memory = MemoryFacade(project_root)

        if action in {"show", "explain"}:
            approved = facts.list_facts(status="approved")
            pending = facts.list_facts(status="pending")
            sessions = SessionSummaryStore(sac_dir).load_recent(limit=3)
            notes = memory.read_project_notes().strip()
            return _format_card(
                "Memory",
                [
                    ("Injected approved facts", str(len(approved))),
                    ("Injected project notes", "yes" if notes else "no"),
                    ("Injected recent sessions", str(len(sessions))),
                    ("Stored pending facts", str(len(pending))),
                    ("Pinned files", str(len(memory.read_pinned_files()))),
                ],
                next_step="/memory review" if pending else "/memory teach <note>",
            )

        if action == "review":
            pending = facts.list_facts(status="pending")
            approved = facts.list_facts(status="approved")
            if not pending:
                return "Memory Review\n-------------\nNo pending facts."
            approved_by_key: dict[str, set[str]] = {}
            for fact in approved:
                approved_by_key.setdefault(fact.key, set()).add(fact.value)
            lines = ["Memory Review", "-------------"]
            for index, fact in enumerate(pending[:10], 1):
                conflict = fact.key in approved_by_key and fact.value not in approved_by_key[fact.key]
                suffix = "  [conflict]" if conflict else ""
                lines.append(f"{index}. [{fact.fact_id[:8]}] {fact.key}: {fact.value[:90]}{suffix}")
            lines.append("")
            lines.append("Next: /memory approve <id>  or  /memory reject <id>")
            return "\n".join(lines)

        if action == "teach":
            text = " ".join(rest).strip()
            if not text:
                return "Usage: /memory teach <non-secret project note>"
            path = memory.add_note(text)
            return _format_card(
                "Memory Note Added",
                [("Path", path.as_posix())],
                next_step="/memory",
            )

        if action in {"approve", "reject"}:
            if not rest:
                return f"Usage: /memory {action} <fact-id>"
            fact = facts.approve(rest[0]) if action == "approve" else facts.reject(rest[0])
            verb = "Approved" if action == "approve" else "Rejected"
            return _format_card(
                f"Memory Fact {verb}",
                [("Fact", f"{fact.key}: {fact.value[:120]}")],
                next_step="/memory review",
            )

        if action == "prune":
            removed = WorkspaceMemoryStore(project_root).clear_stale()
            return _format_card(
                "Memory Pruned",
                [("Workspace entries removed", str(removed))],
                next_step="/memory",
            )

        return "Usage: /memory [review|teach <text>|approve <id>|reject <id>|prune]"
    except Exception as exc:
        return f"Memory command failed: {exc}"


def _slash_demo(project_root: Path) -> str:
    """Return a safe first-run demo path."""
    return "\n".join([
        "Safe First-Run Demo",
        "-------------------",
        "1. /status",
        "2. ask: what does this project do?",
        "3. ask: propose a tiny docs-only improvement",
        "4. /apply   # only if a patch is pending; diff is shown first",
        "5. /undo    # verify rollback works",
        "",
        "No command in this demo auto-applies or commits changes.",
    ])


def _slash_smoke(project_root: Path, args: str = "") -> str:
    """Run opt-in smoke commands from the shell."""
    import subprocess

    parts = args.strip().split()
    if parts[:1] != ["live"]:
        return "Usage: /smoke live"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "safecode.cli", "smoke", "live-provider", "--json"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return _format_card(
            "Live Smoke: TIMEOUT",
            [("Timeout", "60s")],
            next_step="/ready",
            details=["The provider did not answer before the shell smoke timeout."],
        )
    except Exception as exc:
        return _format_card(
            "Live Smoke: ERROR",
            [("Error", str(exc)[:160])],
            next_step="/ready",
        )
    output = (result.stdout or result.stderr).strip()
    title = "Live Smoke: PASS" if result.returncode == 0 else "Live Smoke: FAIL"
    return _format_card(
        title,
        [("Exit code", str(result.returncode))],
        next_step="/status",
        details=[output[:1200] if output else "(no output)"],
    )


def _slash_timeline(project_root: Path, session_id: str = "") -> str:
    """Return the latest or selected agent session timeline."""
    try:
        from safecode.agent.session import AgentSessionStore
        from safecode.report.session_timeline import render_session_timeline
        from safecode.state.journal import AgentJournalStore

        selected = session_id.strip()
        if not selected:
            state = AgentSessionStore(project_root).load()
            selected = state.session_id if state is not None else AgentJournalStore(project_root).latest_session_id() or ""
        if not selected:
            return "No agent session timeline found."
        return render_session_timeline(project_root, selected, limit=8)
    except Exception as exc:
        return f"Timeline unavailable: {exc}"


def _slash_sessions(project_root: Path) -> str:
    """Return a compact list of recent shell and agent sessions."""
    try:
        from safecode.shell_session.store import ShellSessionStore
        from safecode.state.journal import AgentJournalStore

        lines = ["Recent sessions"]
        shell_store = ShellSessionStore(project_root)
        shell_ids = shell_store.list_sessions()[-5:]
        for sid in shell_ids:
            state = shell_store.load(sid)
            if state is not None:
                lines.append(f"shell {sid} turns={len(state.turns)} updated={state.updated_at}")

        journal = AgentJournalStore(project_root)
        if journal.root.exists():
            paths = sorted(journal.root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
            for path in paths:
                if path.is_file() and not path.is_symlink():
                    summary = journal.summary(path.stem)
                    lines.append(f"agent {path.stem} events={summary.event_count} updated={summary.last_timestamp or ''}")
        if len(lines) == 1:
            lines.append("No sessions found.")
        return "\n".join(lines)
    except Exception as exc:
        return f"Sessions unavailable: {exc}"


def _slash_resume(project_root: Path, session_id: str) -> str:
    """Passively resume an agent session from shell."""
    try:
        from safecode.agent.session import AgentSessionStore
        from safecode.agent.loop import AgentLoop
        from safecode.state.journal import AgentJournalStore

        selected = session_id.strip()
        if not selected:
            current = AgentSessionStore(project_root).load()
            selected = current.session_id if current is not None else AgentJournalStore(project_root).latest_session_id() or ""
        if not selected:
            return _format_card(
                "Resume",
                [("Session", "(none)")],
                next_step='Type a request, or run /status.',
            )
        state = AgentLoop(project_root).resume_from(selected)
        return _format_card(
            "Resumed agent session",
            [
                ("Session", state.session_id),
                ("Status", state.status),
                ("Step", f"{state.current_step}/{len(state.plan)}"),
                ("Goal", state.goal[:120]),
            ],
            next_step="/continue",
        )
    except Exception as exc:
        return f"Resume failed: {exc}"


def _slash_task(project_root: Path) -> str:
    """Return current task details."""
    try:
        from safecode.task.store import TaskStore
        from safecode.context.redactor import redact_secrets
        store = TaskStore(project_root)
        current_id = store.current_id()
        if not current_id:
            return _format_card(
                "Task",
                [("Current task", "(none)")],
                next_step='Type a request, or run sac task new "<goal>".',
            )
        state = store.load(current_id)
        if state is None:
            return f"Task {current_id!r} not found."
        last_failure = ""
        if state.iterations:
            last = state.iterations[-1]
            if last.failure_category:
                last_failure = last.failure_category
            elif last.test_exit_code not in (None, 0):
                last_failure = f"test_exit_{last.test_exit_code}"
        pending = (project_root / ".sac" / "pending_patch.json").exists()
        if pending:
            next_step = "/apply"
        elif state.status == "interrupted":
            next_step = "sac resume"
        elif last_failure:
            next_step = "sac fix"
        elif state.status == "applied":
            next_step = "sac commit --ai"
        else:
            next_step = "/continue"
        rows = [
            ("Task", state.task_id),
            ("Goal", redact_secrets(state.goal)[:120]),
            ("Status", state.status),
            ("Iterations", str(len(state.iterations))),
            ("Pending patch", "yes" if pending else "no"),
        ]
        if state.last_command:
            rows.append(("Last command", redact_secrets(state.last_command.command)[:100]))
        if last_failure:
            rows.append(("Recent failure", redact_secrets(last_failure)))
        return _format_card("Task", rows, next_step=next_step)
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
            readiness = _slash_ready(project_root)
            return status + "\n\n" + alias_list + "\n\n" + readiness

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

    if name == "/continue":
        return _slash_continue(project_root), "continue", False

    if name in ("/ready", "/doctor"):
        return _slash_ready(project_root, parts[1] if len(parts) > 1 else ""), "ready", False

    if name == "/memory":
        return _slash_memory(project_root, parts[1] if len(parts) > 1 else ""), "memory", False

    if name == "/demo":
        return _slash_demo(project_root), "demo", False

    if name == "/smoke":
        return _slash_smoke(project_root, parts[1] if len(parts) > 1 else ""), "smoke", False

    if name == "/timeline":
        return _slash_timeline(project_root, parts[1] if len(parts) > 1 else ""), "timeline", False

    if name == "/sessions":
        return _slash_sessions(project_root), "sessions", False

    if name == "/resume":
        return _slash_resume(project_root, parts[1] if len(parts) > 1 else ""), "resume", False

    if name == "/cost":
        return _slash_cost(project_root), "cost", False

    if name == "/budget":
        return _slash_budget(project_root), "budget", False

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
        try:
            data = _build_shell_status_data(project_root)
            next_actions = data.get("next_actions") if isinstance(data, dict) else []
            if isinstance(next_actions, list) and next_actions:
                console.print(f"[dim]Start: /status    Continue: /continue    Next: {next_actions[0]}[/dim]")
            else:
                console.print("[dim]Start: /status    Continue: /continue[/dim]")
        except Exception:
            console.print("[dim]Start: /status    Continue: /continue[/dim]")
        _setup_readline()

    turn_count = 0
    while True:
        # v5.2.1: build task status string for prompt
        _task_str = ""
        try:
            _current_tid = task_store.current_id()
            if _current_tid:
                _task_state = task_store.load(_current_tid)
                if _task_state:
                    _iters = len(_task_state.iterations)
                    _task_str = f"task:{_task_state.status[:4]} · {_iters}i"
        except Exception:
            pass

        line = _read_line(is_tty=is_tty, turn=turn_count, prompt_override=_shell_prompt(turn_count, task_str=_task_str) if _task_str else None)
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
    mode: str = "build",
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

    plan_mode = mode == "plan"
    if plan_mode:
        mode_label = "plan"
    elif full_auto:
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

    # v6.7.0: multi-turn conversational REPL with persistent ConversationBuffer.
    from safecode.agent.conversation import ConversationBuffer
    from safecode.config import SafeCodeConfig

    config = SafeCodeConfig.load(project_root)
    sac_dir = project_root / config.sac_dir
    import uuid
    shell_session_id = uuid.uuid4().hex
    conversation = ConversationBuffer.load(shell_session_id, sac_dir)

    loop = AgentLoop(
        project_root,
        auto_edit=auto_edit,
        full_auto=full_auto,
        command_delay_ms=command_delay_ms,
        no_clarify=True,  # clarification handled interactively in the REPL itself
        plan_mode=plan_mode,
    )

    if is_tty and not json_output:
        console.print(
            "[bold]SafeCode Shell[/bold] [dim](EXPERIMENTAL --agentic v6.7, conversational)[/dim]\n"
            "Type your goal. Use /status, /continue, /exit, /mode, /clear, /compact, /history, /undo."
        )
        if plan_mode:
            console.print("[cyan]Plan mode active. Only read/search/reference tools are available.[/cyan]")
        elif full_auto:
            console.print("[yellow]Full-auto mode active. High-risk commands still blocked.[/yellow]")
        elif auto_edit:
            console.print("[yellow]Auto-edit mode active. Use sac rollback --last to undo.[/yellow]")

    turn_count = 0
    while True:
        turn_count += 1
        prompt = _shell_prompt(turn_count)
        line = _read_line(is_tty=is_tty, turn=turn_count, prompt_override=prompt)
        if line is None:
            break
        goal = line.strip()
        if not goal:
            continue

        # Slash commands in agentic mode
        if goal.startswith("/"):
            if goal in ("/exit", "/quit"):
                if is_tty:
                    console.print("[dim]Exiting agentic shell.[/dim]")
                break
            if goal == "/clear":
                conversation = ConversationBuffer.load(uuid.uuid4().hex, sac_dir)
                if is_tty:
                    console.print("[dim]Conversation cleared.[/dim]")
                continue
            if goal == "/undo":
                try:
                    from safecode.checkpoint.manager import CheckpointManager
                    meta = CheckpointManager(project_root).rollback_last()
                    paths = [op.path for op in meta.file_operations]
                    msg = f"Rolled back: {', '.join(paths)}"
                except Exception as exc:
                    msg = f"Rollback failed: {exc}"
                if is_tty:
                    console.print(msg)
                continue
            if goal == "/history":
                if conversation.is_empty():
                    msg = "No conversation history yet."
                else:
                    msgs = conversation.to_messages()
                    lines_h = [f"Conversation ({len(msgs)} messages, {conversation.turn_count()} turns):"]
                    for m in msgs[-10:]:
                        snippet = str(m.get("content", ""))[:80].replace("\n", " ")
                        lines_h.append(f"  [{m.get('role','?')}] {snippet}")
                    msg = "\n".join(lines_h)
                if is_tty:
                    console.print(msg)
                continue
            if goal == "/compact":
                before = len(conversation.to_messages())
                conversation.compact_now()
                after = len(conversation.to_messages())
                if is_tty:
                    console.print(f"[dim]Conversation compacted: {before} -> {after} messages.[/dim]")
                continue
            if goal.startswith(("/status", "/continue", "/memory", "/ready", "/doctor", "/demo", "/smoke", "/timeline", "/sessions", "/resume")):
                response, _intent, _exit = _handle_slash_command(goal, project_root, None, is_tty=is_tty)
                if json_output:
                    print(render_json(CLIJSONResponse(command="shell --agentic slash", status="success", data={"response": response})))
                    break
                if is_tty:
                    console.print(response)
                continue
            if goal.startswith("/mode"):
                parts = goal.split(None, 1)
                if len(parts) == 1:
                    msg = f"Current mode: {'plan' if plan_mode else 'build'}"
                else:
                    requested = parts[1].strip().lower()
                    if requested not in {"plan", "build"}:
                        msg = "Usage: /mode plan|build"
                    else:
                        plan_mode = requested == "plan"
                        loop = AgentLoop(
                            project_root,
                            auto_edit=False if plan_mode else auto_edit,
                            full_auto=False if plan_mode else full_auto,
                            command_delay_ms=command_delay_ms,
                            no_clarify=True,
                            plan_mode=plan_mode,
                        )
                        msg = (
                            "Switched to plan mode. Writes and commands are unavailable."
                            if plan_mode
                            else "Switched to build mode. Approval settings restored."
                        )
                if is_tty:
                    console.print(msg)
                elif json_output:
                    print(render_json(CLIJSONResponse(command="shell --agentic /mode", status="success", data={"message": msg, "mode": "plan" if plan_mode else "build"})))
                    break
                continue
            # Unknown slash command — fall through as a question
            if is_tty:
                console.print(f"[yellow]Unknown command: {goal!r}. Use /exit, /clear, /undo, /history.[/yellow]")
            continue

        # Append user turn to conversation buffer
        conversation.append_user(goal)

        step_updates: list[str] = []

        def on_step(result, _su=step_updates):
            obs = result.observation[:120]
            _su.append(obs)
            if is_tty and not json_output and auto_edit:
                action = result.state.pending_action or {}
                write_calls = int(action.get("write_calls", "0") or "0") if action.get("type") == "native_turn" else 0
                if write_calls:
                    console.print(f"  [green]✓[/green] {write_calls} file(s) edited")

        try:
            if is_tty and not json_output:
                from rich.status import Status
                with Status("[bold blue]Thinking...", spinner="dots"):
                    result = loop.run(goal, max_steps=8, on_step=on_step, conversation=conversation)
            else:
                result = loop.run(goal, max_steps=8, on_step=on_step, conversation=conversation)
        except (FileNotFoundError, ValueError) as exc:
            errmsg = str(exc)
            conversation.append_assistant(f"Error: {errmsg}")
            if json_output:
                print(render_json(CLIJSONResponse(command="shell --agentic", status="error", error=errmsg)))
                return 1
            if is_tty:
                console.print(f"[red]{errmsg}[/red]")
            continue

        # Build assistant reply from step observations
        observations = [s.observation for s in result.steps if s.observation]
        for step in result.steps:
            action = step.state.pending_action or {}
            if action.get("type") == "native_turn" and step.observation:
                conversation.append_tool_result("native_turn", step.observation)
        agent_reply = "\n".join(observations) if observations else f"Done ({result.stopped_reason})"
        conversation.append_assistant(agent_reply)

        if json_output:
            status = result.stopped_reason if result.stopped_reason in ("completed", "approval_required") else "stopped"
            data: dict = {
                "session_id": result.state.session_id,
                "stopped_reason": result.stopped_reason,
                "steps_count": len(result.steps),
                "status": result.state.status,
                "step_updates": step_updates,
                "turn": turn_count,
                "conversation_turns": conversation.turn_count(),
                "mode": "plan" if plan_mode else "build",
            }
            last_typed = loop.last_typed_result
            if last_typed is not None:
                data["last_typed_result"] = last_typed.model_dump()
            session_cost_json = loop.session_cost()
            if session_cost_json and (session_cost_json.prompt_tokens or session_cost_json.completion_tokens):
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
            # In JSON mode stop after one turn (caller drives the loop)
            break

        # TTY display
        for idx, step_result in enumerate(result.steps, start=1):
            if step_result.observation:
                console.print(f"[dim]Step {idx}:[/dim] {step_result.observation}")

        session_cost = loop.session_cost()
        cost_parts: list[str] = []
        if session_cost and (session_cost.prompt_tokens or session_cost.completion_tokens):
            cost_str = _format_cost(session_cost.prompt_tokens, session_cost.completion_tokens, session_cost.cache_read_tokens)
            if cost_str:
                cost_parts.append(cost_str)
        if loop._native_write_count:
            cost_parts.append(f"{loop._native_write_count} file(s) edited")
        if cost_parts or result.stopped_reason not in ("completed", "max_steps_reached"):
            console.print(f"[dim]{result.stopped_reason}" + (f" · {' · '.join(cost_parts)}" if cost_parts else "") + "[/dim]")

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
        mode: str = typer.Option(
            "build",
            "--mode",
            help="[EXPERIMENTAL] Agentic mode: plan (read-only tools) or build (normal approval flow).",
        ),
    ) -> None:
        """[EXPERIMENTAL] Start an interactive AI shell session.

        Ask natural-language questions, run /status, /apply, /debug, and more.
        All mutation paths require explicit approval. No auto-apply ever.

        With --agentic, user input becomes the goal for an AgentLoop.run() invocation
        (the same loop sac agent run drives). Existing shell behavior is unchanged
        without --agentic.

        With --mode plan, only read/search/reference native tools are registered.

        With --auto-edit (implies --agentic), edit_file and write_file execute
        without per-call prompts. Use 'sac rollback --last' or '/undo' to undo.

        With --full-auto (implies --agentic), run_command also executes automatically
        within policy limits. A preview line is printed and a grace period allows
        Ctrl-C abort. High-risk commands are still blocked. Cannot be persisted.
        """
        project_root = Path.cwd()
        is_tty = sys.stdin.isatty() and sys.stdout.isatty() and not non_tty
        delay_ms = max(0, min(2000, command_delay_ms))
        mode_value = mode.strip().lower()
        if mode_value not in {"plan", "build"}:
            console.print("[red]--mode must be 'plan' or 'build'.[/red]")
            raise typer.Exit(code=2)
        if mode_value == "plan":
            auto_edit = False
            full_auto = False
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
                mode=mode_value,
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
