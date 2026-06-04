"""EXPERIMENTAL: Natural-language intent router for sac shell (v4.9.1+).

Routes ordinary user input to one of the following intents:
  ask, edit, fix, run, status, apply, commit, debug, overview, exit

Design principles:
- Prefer structured internal calls over shelling out to command strings.
- Ambiguous intent defaults to read-only 'ask'; never directly triggers mutation.
- Write-class actions (edit, fix, run, apply, commit) require explicit confirmation.
- Profile-based test/lint/typecheck/build routing is preserved.
- Mock provider is used for deterministic tests.

All surfaces in this module are EXPERIMENTAL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

_READ_INTENTS = frozenset({"ask", "status", "overview", "debug", "exit"})
_WRITE_INTENTS = frozenset({"edit", "fix", "run", "apply", "commit"})
_ALL_INTENTS = _READ_INTENTS | _WRITE_INTENTS

# Keywords that strongly suggest each intent category
_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("exit",    [r"\bexit\b", r"\bquit\b", r"\bbye\b"]),
    ("status",  [r"\bstatus\b", r"\bwhat.s (going on|happening)\b", r"\bstate\b"]),
    ("overview",[r"\boverview\b", r"\bstructure\b", r"\bwhat is this (project|repo|codebase)\b",
                 r"\bexplain (this|the) (project|repo|codebase)\b", r"\bproject layout\b"]),
    ("debug",   [r"\bdebug\b", r"\blast failure\b", r"\berror\b", r"\bwhat (went wrong|failed)\b",
                 r"\bshow (me )?(the )?(last )?(error|failure|bug)\b"]),
    ("apply",   [r"\bapply( the)? patch\b", r"\bapply (it|this)\b"]),
    ("commit",  [r"\bcommit\b"]),
    ("run",     [r"\brun\b", r"\bexecute\b", r"\btest\b", r"\blint\b", r"\btypecheck\b", r"\bbuild\b"]),
    ("fix",     [r"\bfix\b", r"\brepair\b", r"\bsolve( the)? (bug|issue|error|failure)\b"]),
    ("edit",    [r"\bedit\b", r"\bchange\b", r"\bmodify\b", r"\bupdate\b", r"\brefactor\b",
                 r"\bwrite\b", r"\bcreate\b", r"\badd\b", r"\bremove\b", r"\bdelete\b",
                 r"\bimplement\b", r"\bmake (the|a|an)\b", r"\bsmallest (safe )?(fix|change)\b"]),
    ("ask",     [r"\bwhat\b", r"\bhow\b", r"\bwhy\b", r"\bwhere\b", r"\bwho\b",
                 r"\bshow me\b", r"\bfind\b", r"\bexplain\b", r"\bdescribe\b", r"\blist\b",
                 r"\btell me\b", r"\bhelp\b"]),
]


def classify_intent(user_input: str) -> str:
    """Classify the user's natural-language input into an intent.

    Ambiguous or unrecognized input defaults to 'ask' (read-only).
    Order matters: exit and mutation checks before read-only fallback.
    """
    text = user_input.strip().lower()
    if not text:
        return "ask"

    for intent, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text):
                return intent

    return "ask"


# ---------------------------------------------------------------------------
# Confirmation helper
# ---------------------------------------------------------------------------


def _ask_confirm(prompt: str, *, is_tty: bool) -> bool:
    """Ask for confirmation in TTY mode. Always returns False in non-TTY mode."""
    if not is_tty:
        return False
    try:
        answer = input(prompt).strip().lower()
        return answer in ("y", "yes")
    except EOFError:
        return False


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------


def _handle_ask_intent(user_input: str, project_root: Path) -> str:
    """Route to the SafeCode ask primitive (read-only)."""
    try:
        from safecode.agent.orchestrator import AgentOrchestrator
        result = AgentOrchestrator(project_root).ask(user_input)
        content = getattr(result, "content", None) or str(result)
        return str(content)
    except Exception as exc:
        return f"Ask failed: {exc}\nRun: sac ask \"{user_input}\""


def _handle_edit_intent(
    user_input: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> str:
    """Route to edit after confirmation (write-class)."""
    confirmed = _ask_confirm(
        f"Propose edit: \"{user_input[:80]}\"? [y/N]: ", is_tty=is_tty
    )
    if not confirmed:
        return f"Edit not confirmed. Run: sac edit \"{user_input[:80]}\""
    try:
        from safecode.agent.orchestrator import AgentOrchestrator
        from safecode.task.wiring import get_or_create_current_task, record_edit_on_task
        task = get_or_create_current_task(project_root, "edit", user_input)
        result = AgentOrchestrator(project_root).edit(user_input)
        try:
            record_edit_on_task(project_root, task.task_id, result.proposal.id)
        except Exception:
            pass
        return (
            f"Patch proposed: {result.pending_patch_path}\n"
            f"Review the diff, then run /apply or: sac apply"
        )
    except Exception as exc:
        return f"Edit failed: {exc}\nRun: sac edit \"{user_input[:80]}\""


def _handle_fix_intent(
    user_input: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> str:
    """Route to fix after confirmation (write-class)."""
    confirmed = _ask_confirm("Run fix loop? [y/N]: ", is_tty=is_tty)
    if not confirmed:
        return "Fix not confirmed. Run: sac fix"
    try:
        from safecode.cli_fix import run_fix
        code = run_fix(project_root)
        if code == 0:
            return "Fix completed. Run /apply or: sac apply"
        return f"Fix exited with code {code}. Run: sac status"
    except Exception as exc:
        return f"Fix failed: {exc}\nRun: sac fix"


def _handle_run_intent(
    user_input: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> str:
    """Route to profile-based run after confirmation (write-class)."""
    # Detect profile suite
    suite = _detect_suite_from_input(user_input)
    if suite:
        confirmed = _ask_confirm(f"Run profile suite '{suite}'? [y/N]: ", is_tty=is_tty)
        if not confirmed:
            return f"Run not confirmed. Run: sac run --suite {suite}"
        import subprocess, sys as _sys
        result = subprocess.run(
            [_sys.executable, "-m", "safecode.cli", "run", "--suite", suite],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        out = (result.stdout + result.stderr).strip()
        return f"Run --suite {suite} exited {result.returncode}.\n{out}"
    return f"Ambiguous run intent. Use: sac run --suite test|lint|typecheck|build"


def _detect_suite_from_input(text: str) -> str | None:
    """Detect a named profile suite from natural language."""
    text = text.lower()
    for suite in ("typecheck", "lint", "build", "test"):
        if suite in text:
            return suite
    return None


def _handle_apply_intent(
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> str:
    """Delegate to the /apply slash handler."""
    from safecode.cli_shell import _slash_apply
    return _slash_apply(project_root, task_id, is_tty=is_tty)


def _handle_commit_intent(
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> str:
    """Delegate to the /commit slash handler."""
    from safecode.cli_shell import _slash_commit
    return _slash_commit(project_root, task_id, is_tty=is_tty)


def _handle_status_intent(project_root: Path) -> str:
    from safecode.cli_shell import _slash_status
    return _slash_status(project_root)


def _handle_overview_intent(project_root: Path) -> str:
    from safecode.cli_shell import _slash_overview
    return _slash_overview(project_root)


def _handle_debug_intent(project_root: Path, task_id: Optional[str]) -> str:
    from safecode.cli_shell import _slash_debug
    return _slash_debug(project_root, task_id)


# ---------------------------------------------------------------------------
# Main router entry point
# ---------------------------------------------------------------------------


def route_input(
    user_input: str,
    project_root: Path,
    task_id: Optional[str],
    *,
    is_tty: bool,
) -> tuple[str, str, bool]:
    """Route user input to the appropriate handler.

    Returns (response, intent, exit_shell).
    Ambiguous intent defaults to read-only 'ask'; never directly mutates.
    """
    intent = classify_intent(user_input)

    if intent == "exit":
        return "Exiting shell.", "exit", True

    if intent == "status":
        return _handle_status_intent(project_root), "status", False

    if intent == "overview":
        return _handle_overview_intent(project_root), "overview", False

    if intent == "debug":
        return _handle_debug_intent(project_root, task_id), "debug", False

    if intent == "apply":
        return _handle_apply_intent(project_root, task_id, is_tty=is_tty), "apply", False

    if intent == "commit":
        return _handle_commit_intent(project_root, task_id, is_tty=is_tty), "commit", False

    if intent == "run":
        return (
            _handle_run_intent(user_input, project_root, task_id, is_tty=is_tty),
            "run",
            False,
        )

    if intent == "fix":
        return (
            _handle_fix_intent(user_input, project_root, task_id, is_tty=is_tty),
            "fix",
            False,
        )

    if intent == "edit":
        return (
            _handle_edit_intent(user_input, project_root, task_id, is_tty=is_tty),
            "edit",
            False,
        )

    # Default: ask (read-only)
    return _handle_ask_intent(user_input, project_root), "ask", False
