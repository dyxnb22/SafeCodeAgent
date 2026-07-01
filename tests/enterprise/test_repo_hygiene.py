"""Mechanical checks for the repository's agent governance contract."""

from datetime import date
import json
from pathlib import Path
import re
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
FORBIDDEN_TRACKED_DIRECTORY_NAMES = {
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
}
FORBIDDEN_TRACKED_SUFFIXES = {
    ".bak",
    ".log",
    ".orig",
    ".pem",
    ".rej",
    ".tmp",
}
FORBIDDEN_TRACKED_FILENAMES = {
    ".coverage",
    ".DS_Store",
    "coverage.xml",
    "tsconfig.tsbuildinfo",
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
    assert "enterprise-docs/platform-architecture-v2.md" in skill
    assert "Maintained Final Documentation" in skill


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
        "## Implemented Capability Map",
        "## Task-To-Context Routing",
        "## Impact Check Before Code Changes",
        "## Broad Scan Triggers",
        "## Update Triggers",
    ):
        assert heading in context


def test_progress_state_is_valid() -> None:
    progress = json.loads(_read(".agents/context/progress.json"))
    context = _read(".agents/context/project-context.md")

    assert progress["schema_version"] == 1
    date.fromisoformat(progress["updated_at"])
    assert progress["implemented_baseline_tag"] == "v7.1.5"

    current = progress["current"]
    assert current["status"] in {"ready", "in_progress", "blocked", "completed"}
    assert current["stage"] in progress["stages"]
    if current.get("next_delivery_task"):
        assert current["next_delivery_task"] in context

    if current["status"] == "ready":
        assert current["active_task"] is None
        assert progress["stages"][current["stage"]] == "ready"
    elif current["status"] == "completed":
        assert current["active_task"] is None
        assert progress["stages"][current["stage"]] == "completed"
    else:
        assert current["active_task"]
        date.fromisoformat(current["active_task"]["started_at"])
    if current["status"] == "blocked":
        assert progress["blockers"]

    portfolio = progress.get("portfolio_track")
    if portfolio:
        assert portfolio["status"] in {"ready", "in_progress", "blocked", "completed"}
        if portfolio.get("next_delivery_task"):
            assert portfolio["next_delivery_task"] in context
        if portfolio["status"] == "ready":
            assert portfolio["active_task"] is None
        elif portfolio["status"] in {"in_progress", "blocked"}:
            assert portfolio["active_task"]
            date.fromisoformat(portfolio["active_task"]["started_at"])

    assert progress["stages"]["v1.0"] == "completed"
    if progress["stages"].get("v2.0") != "completed":
        assert progress["stages"]["v2.0"] in {"planned", "ready", "in_progress"}

    completed = progress["completed_delivery_tasks"]
    completed_ids = [task["id"] for task in completed]
    assert len(completed_ids) == len(set(completed_ids))
    for task in completed:
        assert re.fullmatch(r"v\d+\.\d+\.\d+-T\d+", task["id"])
        date.fromisoformat(task["completed_at"])
        assert task["evidence"].strip()

    assert len(progress["recent_maintenance"]) <= 10
    for task in progress["recent_maintenance"]:
        assert task["id"].strip()
        date.fromisoformat(task["completed_at"])
        assert task["evidence"].strip()

    for decision in progress["decisions_required"]:
        assert decision["required_before"].strip()
        assert decision["summary"].strip()

    verification = progress["last_verification"]
    date.fromisoformat(verification["recorded_at"])
    assert verification["command"].strip()
    assert verification["result"].strip()
    if progress["stages"]["v1.1"] == "completed":
        assert verification["command"] in {
            "PYTHONPATH=src python3 -m pytest -q",
            "uv run --extra enterprise python -m pytest -q",
        }
        assert "passed" in verification["result"]


def test_feature_frozen_tree_does_not_restore_delivery_backlogs() -> None:
    retired = (
        "product-planning/version-roadmap.md",
        "product-planning/milestone-acceptance.md",
        "product-planning/execution-backlog.md",
        "product-planning/post-ga-portfolio-roadmap.md",
    )
    for relative_path in retired:
        assert not (ROOT / relative_path).exists()


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
        if not (ROOT / path).is_file():
            continue
        parts = path.parts

        if path.name in FORBIDDEN_TRACKED_FILENAMES:
            violations.append(raw_path)
        elif any(part in FORBIDDEN_TRACKED_DIRECTORY_NAMES for part in parts[:-1]):
            violations.append(raw_path)
        elif (
            path.name == ".env"
            or path.name.endswith(".env")
            or (path.name.startswith(".env.") and not path.name.endswith(".example"))
        ):
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


@pytest.mark.subprocess
def test_no_tracked_sac_runtime_paths() -> None:
    """Runtime .sac/ trees must not be committed; use fixtures/ for example seeds."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    tracked_sac = [
        raw_path
        for raw_path in result.stdout.split("\0")
        if raw_path and "/.sac/" in f"/{raw_path}/"
    ]

    assert not tracked_sac, f"tracked .sac runtime paths: {tracked_sac}"
