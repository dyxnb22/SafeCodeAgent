"""Rendering helpers for the conversational shell."""

from __future__ import annotations

import re
from typing import Any


def welcome_text(manifest: Any, *, resumed: bool, provider: str = "", model: str = "") -> str:
    """Render the short first screen for an interactive shell."""
    state = "resumed" if resumed else "new"
    bits = [
        f"SafeCode {manifest.session_id[:8]}",
        manifest.title,
        state,
        manifest.mode,
    ]
    if provider:
        bits.append(f"provider={provider}")
    if model:
        bits.append(f"model={model}")
    return " · ".join(str(bit) for bit in bits if bit)


def resume_hint_text(manifest: Any) -> str:
    """Explain what was restored when a session is resumed."""
    lines = [f"Resumed {manifest.session_id[:12]}: {manifest.title}"]
    if manifest.last_response:
        snippet = " ".join(manifest.last_response.split())[:160]
        lines.append(f"Last response: {snippet}")
    if manifest.status in {"waiting_for_approval", "interrupted"}:
        lines.append("Next: use /continue to inspect the blocker or advance one safe step.")
    return "\n".join(lines)


def phase_for_step(result: Any) -> str:
    """Map an agent step to a stable, human-readable activity phase."""
    action = result.state.pending_action or {}
    observation = str(getattr(result, "observation", ""))
    marker = re.match(r"\s*\[tool:([a-zA-Z0-9_-]+)\]", observation)
    tool_markers = marker.group(1) if marker else ""
    text = f"{action.get('tool_name', '')} {action.get('route', '')} {tool_markers}".lower()
    if getattr(result.state, "status", "") == "completed":
        return "Completed"
    if any(word in text for word in ("test", "pytest", "validate")):
        return "Testing"
    if any(word in text for word in ("edit", "write", "patch", "apply")):
        return "Editing"
    if any(word in text for word in ("search", "grep", "find", "list")):
        return "Searching"
    if any(word in text for word in ("read", "context", "inspect")):
        return "Reading"
    return "Thinking"


def history_text(conversation: Any, *, limit: int = 10) -> str:
    if conversation.is_empty():
        return "No conversation history yet."
    messages = conversation.to_messages()
    lines = [f"Conversation ({len(messages)} messages, {conversation.turn_count()} turns):"]
    for message in messages[-limit:]:
        snippet = str(message.get("content", ""))[:100].replace("\n", " ")
        lines.append(f"  [{message.get('role', '?')}] {snippet}")
    return "\n".join(lines)


def session_list_text(manifests: list[Any], *, current_id: str = "") -> str:
    if not manifests:
        return "No sessions found."
    lines = ["Recent sessions", "---------------"]
    for manifest in manifests:
        marker = "*" if manifest.session_id == current_id else " "
        lines.append(
            f"{marker} {manifest.session_id[:12]}  {manifest.title[:42]}  "
            f"[{manifest.status}, {manifest.turns} turns]"
        )
    lines.append("\nUse /resume <id>, /new, or /rename <title>.")
    return "\n".join(lines)


def turn_summary_text(
    *,
    response: str,
    files: list[str],
    tests: list[str],
    stopped_reason: str,
    cost: str = "",
) -> str:
    lines = [response.strip() or f"Done ({stopped_reason})"]
    details: list[str] = []
    if files:
        details.append(f"Files: {', '.join(files[:8])}")
    if tests:
        details.append(f"Tests: {', '.join(tests[:4])}")
    if cost:
        details.append(f"Cost: {cost}")
    if stopped_reason not in {"completed", "max_steps_reached"}:
        details.append(f"Status: {stopped_reason}")
    if details:
        lines.extend(["", "  " + " | ".join(details)])
    return "\n".join(lines)
