"""Mechanical checks for the repository's agent governance contract."""

from datetime import date
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent
GOVERNANCE_MARKER = "<!-- governance-contract:v2 -->"
PROJECT_CONTEXT_MARKER = "<!-- project-context:v1 -->"

CONTEXT_FILES = (
    "AGENTS.md",
    ".agents/skills/current/SKILL.md",
    ".agents/context/project-context.md",
    ".agents/context/progress.json",
)

LEGACY_CLAUDE_POLICY_FILES = (
    ".claude/CLAUDE.md",
    ".claude/rules/general-rules.md",
    ".claude/skills/current/SKILL.md",
    ".claude/skills/shared/core-runtime.md",
)

FORBIDDEN_TEST_DIRECTORIES = {"temp", "debug", "scratch", "generated"}
FORBIDDEN_DOC_DIRECTORIES = {"worklog", "evidence"}
FORBIDDEN_TRACKED_SUFFIXES = {
    ".bak",
    ".log",
    ".orig",
    ".rej",
    ".tmp",
}
FORBIDDEN_TRACKED_FILENAMES = {
    ".coverage",
    "coverage.xml",
}


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_agent_entrypoints_use_canonical_governance() -> None:
    agents = _read("AGENTS.md")
    claude = _read("CLAUDE.md")
    cursor = _read(".cursor/rules/00-project-governance.mdc")
    skill = _read(".agents/skills/current/SKILL.md")

    assert GOVERNANCE_MARKER in agents
    assert "@AGENTS.md" in claude
    assert "@.agents/skills/current/SKILL.md" in claude
    assert "@.agents/context/project-context.md" in claude
    assert "@.agents/context/progress.json" in claude
    assert "alwaysApply: true" in cursor
    assert "`AGENTS.md` is the canonical repository rule source" in cursor
    for path in CONTEXT_FILES[2:]:
        assert path in agents
        assert path in cursor
        assert path in skill


def test_tool_entrypoints_remain_thin() -> None:
    claude_lines = _read("CLAUDE.md").splitlines()
    cursor_lines = _read(".cursor/rules/00-project-governance.mdc").splitlines()

    assert len(claude_lines) <= 16
    assert len(cursor_lines) <= 20


def test_project_context_is_compact_and_routable() -> None:
    context = _read(".agents/context/project-context.md")

    assert PROJECT_CONTEXT_MARKER in context
    assert len(context.splitlines()) <= 250
    for heading in (
        "## Source Precedence",
        "## Architecture At A Glance",
        "## Feature And Stage Map",
        "## Task-To-Context Routing",
        "## Impact Check Before Code Changes",
        "## Broad Scan Triggers",
        "## Update Triggers",
    ):
        assert heading in context


def test_progress_state_is_valid_and_matches_backlog() -> None:
    progress = json.loads(_read(".agents/context/progress.json"))
    backlog = _read("product-planning/execution-backlog.md")
    context = _read(".agents/context/project-context.md")

    assert progress["schema_version"] == 1
    date.fromisoformat(progress["updated_at"])
    assert progress["implemented_baseline_tag"] == "v7.1.5"

    current = progress["current"]
    assert current["status"] in {"ready", "in_progress", "blocked"}
    assert current["stage"] in progress["stages"]
    assert current["next_delivery_task"] in backlog
    assert current["next_delivery_task"] in context

    if current["status"] == "ready":
        assert current["active_task"] is None
    else:
        assert current["active_task"]
        date.fromisoformat(current["active_task"]["started_at"])
    if current["status"] == "blocked":
        assert progress["blockers"]

    assert progress["stages"]["v1.0"] == "completed"
    assert progress["stages"]["v2.0"] in {"planned", "ready", "in_progress"}

    completed = progress["completed_delivery_tasks"]
    completed_ids = [task["id"] for task in completed]
    assert len(completed_ids) == len(set(completed_ids))
    for task in completed:
        assert task["id"] in backlog
        date.fromisoformat(task["completed_at"])
        assert task["evidence"].strip()

    assert len(progress["recent_maintenance"]) <= 10
    for task in progress["recent_maintenance"]:
        assert task["id"].strip()
        date.fromisoformat(task["completed_at"])
        assert task["evidence"].strip()

    for decision in progress["decisions_required"]:
        assert decision["required_before"] in backlog
        assert decision["summary"].strip()

    verification = progress["last_verification"]
    date.fromisoformat(verification["recorded_at"])
    assert verification["command"].strip()
    assert verification["result"].strip()


@pytest.mark.parametrize("relative_path", LEGACY_CLAUDE_POLICY_FILES)
def test_legacy_claude_policy_copies_are_removed(relative_path: str) -> None:
    assert not (ROOT / relative_path).exists()


def test_forbidden_scratch_directories_are_absent() -> None:
    for name in FORBIDDEN_TEST_DIRECTORIES:
        assert not (ROOT / "tests" / name).exists()
    for name in FORBIDDEN_DOC_DIRECTORIES:
        assert not (ROOT / "docs" / name).exists()


@pytest.mark.subprocess
def test_temporary_outputs_are_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    violations: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = Path(raw_path)
        parts = path.parts

        if path.name in FORBIDDEN_TRACKED_FILENAMES:
            violations.append(raw_path)
        elif path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES:
            violations.append(raw_path)
        elif parts and parts[0] == "tests" and any(
            part in FORBIDDEN_TEST_DIRECTORIES for part in parts[1:-1]
        ):
            violations.append(raw_path)
        elif parts and parts[0] == "docs" and any(
            part in FORBIDDEN_DOC_DIRECTORIES for part in parts[1:-1]
        ):
            violations.append(raw_path)

    assert not violations, f"temporary artifacts are tracked: {violations}"
