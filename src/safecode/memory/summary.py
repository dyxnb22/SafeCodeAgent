"""Build session summaries and format them for context injection (v6.2.0)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from safecode.context.redactor import redact_secrets
from safecode.memory.session_store import SessionSummary

_FILE_RE = re.compile(
    r"(?:edit|write|patch|applying|modified|updated)\s+[`'\"]?([a-zA-Z0-9_./\\-]+\.[a-zA-Z]{1,6})[`'\"]?",
    re.IGNORECASE,
)
_CMD_RE = re.compile(
    r"(?:run|running|executed?)\s+[`'\"]([^`'\"]{1,80})[`'\"]",
    re.IGNORECASE,
)
_TEST_PASS_RE = re.compile(r"passed|tests? pass|all.*tests? pass", re.IGNORECASE)
_TEST_FAIL_RE = re.compile(r"failed|tests? fail|assertion error|FAILED", re.IGNORECASE)

_MAX_CONTEXT_CHARS = 1500
_MAX_RECENT_FOR_CONTEXT = 3


def build_session_summary(
    session_id: str,
    goal: str,
    step_observations: list[str],
    stopped_reason: str,
    started_at: str,
    ended_at: str | None = None,
    *,
    approved_patches: int = 0,
) -> SessionSummary:
    """Derive a SessionSummary from raw observations collected during run()."""
    touched_files: list[str] = []
    commands_run: list[str] = []
    tests_passed: bool | None = None

    for obs in step_observations:
        safe_obs = redact_secrets(obs)
        for match in _FILE_RE.findall(safe_obs):
            if match not in touched_files and not _looks_sensitive(match):
                touched_files.append(match)
        for match in _CMD_RE.findall(safe_obs):
            cmd = match.strip()
            if cmd and cmd not in commands_run and not _looks_sensitive(cmd):
                commands_run.append(cmd)
        if _TEST_PASS_RE.search(safe_obs):
            tests_passed = True
        elif _TEST_FAIL_RE.search(safe_obs) and tests_passed is None:
            tests_passed = False

    return SessionSummary(
        session_id=session_id,
        goal=redact_secrets(goal[:200]),
        started_at=started_at,
        ended_at=ended_at or datetime.now(timezone.utc).isoformat(),
        stopped_reason=stopped_reason,
        steps=len(step_observations),
        touched_files=touched_files[:20],
        commands_run=commands_run[:10],
        tests_passed=tests_passed,
        approved_patches=approved_patches,
    )


def format_memory_context(summaries: list[SessionSummary], max_chars: int = _MAX_CONTEXT_CHARS) -> str:
    """Format recent session summaries as a bounded context block for injection."""
    if not summaries:
        return ""
    header = "## Recent Session Memory (last sessions)"
    blocks: list[str] = []
    chars = len(header)
    for summary in summaries[:_MAX_RECENT_FOR_CONTEXT]:
        block = summary.to_context_block()
        if chars + len(block) + 4 > max_chars:
            break
        blocks.append(block)
        chars += len(block) + 4
    if not blocks:
        return ""
    return header + "\n" + "\n\n".join(blocks)


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    sensitive = {"token", "secret", "password", "api_key", "apikey", "private_key", "credential"}
    return any(word in lowered for word in sensitive)
