"""EXPERIMENTAL: Project overview/context builder for sac shell (v4.9.2+).

Aggregates structured signals about the project without RAG or embeddings:
  - Stack detection (Python/TypeScript/Go/Rust/unknown)
  - Git status (branch, dirty flag, recent commits)
  - Project profile (test/lint/typecheck/build commands)
  - Detected entrypoints and test directories
  - Top-level docs and README
  - Pinned memory files
  - Current task state
  - Recent failures
  - High-signal files (list only, no content)

Context is bounded by _MAX_OVERVIEW_BYTES. Skipped signals are reported
in `skipped_signals` so they are visible in /debug output.

Secrets are redacted via the existing redact_secrets() mechanism.
Path policy respects the project root boundary (no traversal outside root).
All surfaces in this module are EXPERIMENTAL.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.context.redactor import redact_secrets

_MAX_OVERVIEW_BYTES = 8_000
_MAX_RECENT_COMMITS = 5
_MAX_HIGH_SIGNAL_FILES = 20
_MAX_RECENT_FAILURES = 3

# High-signal file globs (in priority order)
_HIGH_SIGNAL_GLOBS = [
    "README*",
    "*.md",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "setup.py",
    "setup.cfg",
    "requirements*.txt",
    "Makefile",
    "Dockerfile",
    ".github/workflows/*.yml",
]

# Stack detection markers
_STACK_MARKERS: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("setup.cfg", "python"),
    ("requirements.txt", "python"),
    ("package.json", "typescript"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
]


@dataclass(frozen=True)
class ProjectOverview:
    """Structured project overview built from local signals (EXPERIMENTAL, v4.9.2+).

    All fields are safe to display; secrets are pre-redacted.
    `skipped_signals` lists signals that were omitted due to context budget or path policy.
    """

    project_root: str
    stack: str
    git_branch: str
    git_dirty: bool
    recent_commits: list[str]
    profile_commands: dict[str, str]
    entrypoints: list[str]
    test_dirs: list[str]
    high_signal_files: list[str]
    pinned_files: list[str]
    current_task: dict[str, Any]
    recent_failures: list[str]
    skipped_signals: list[str]

    def render_text(self) -> str:
        """Render a bounded plain-text overview suitable for shell output."""
        lines: list[str] = ["[EXPERIMENTAL] Project Overview"]
        lines.append(f"Root: {self.project_root}")
        lines.append(f"Stack: {self.stack}")
        if self.git_branch:
            dirty_marker = " (dirty)" if self.git_dirty else ""
            lines.append(f"Branch: {self.git_branch}{dirty_marker}")
        if self.recent_commits:
            lines.append("Recent commits:")
            for c in self.recent_commits[:_MAX_RECENT_COMMITS]:
                lines.append(f"  {c}")
        if self.profile_commands:
            lines.append("Profile commands:")
            for kind, cmd in self.profile_commands.items():
                lines.append(f"  {kind}: {cmd}")
        if self.entrypoints:
            lines.append(f"Entrypoints: {', '.join(self.entrypoints[:5])}")
        if self.test_dirs:
            lines.append(f"Test dirs: {', '.join(self.test_dirs[:5])}")
        if self.high_signal_files:
            lines.append("High-signal files:")
            for f in self.high_signal_files[:_MAX_HIGH_SIGNAL_FILES]:
                lines.append(f"  {f}")
        if self.pinned_files:
            lines.append(f"Pinned: {', '.join(self.pinned_files[:5])}")
        if self.current_task:
            task_id = self.current_task.get("task_id", "(none)")
            goal = self.current_task.get("goal", "(none)")
            status = self.current_task.get("status", "(none)")
            lines.append(f"Task: {task_id} | {status} | {goal}")
        if self.recent_failures:
            lines.append("Recent failures:")
            for f in self.recent_failures[:_MAX_RECENT_FAILURES]:
                lines.append(f"  {f}")
        if self.skipped_signals:
            lines.append(f"(Skipped due to budget: {', '.join(self.skipped_signals)})")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "stack": self.stack,
            "git_branch": self.git_branch,
            "git_dirty": self.git_dirty,
            "recent_commits": self.recent_commits,
            "profile_commands": self.profile_commands,
            "entrypoints": self.entrypoints,
            "test_dirs": self.test_dirs,
            "high_signal_files": self.high_signal_files,
            "pinned_files": self.pinned_files,
            "current_task": self.current_task,
            "recent_failures": self.recent_failures,
            "skipped_signals": self.skipped_signals,
        }


# ---------------------------------------------------------------------------
# Signal collectors (each safe, bounded, fail-silent)
# ---------------------------------------------------------------------------


def _detect_stack(project_root: Path) -> str:
    for filename, stack in _STACK_MARKERS:
        if (project_root / filename).exists():
            return stack
    return "unknown"


def _git_branch(project_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _git_dirty(project_root: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False


def _git_recent_commits(project_root: Path, n: int = _MAX_RECENT_COMMITS) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "log", f"-{n}", "--oneline"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return [
                redact_secrets(line)
                for line in r.stdout.strip().splitlines()
                if line.strip()
            ]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []


def _profile_commands(project_root: Path) -> dict[str, str]:
    try:
        from safecode.project.profile import load_profile
        profile = load_profile(project_root)
        if profile is None:
            return {}
        result: dict[str, str] = {}
        for kind in ("test", "lint", "typecheck", "build"):
            cmd = getattr(profile, kind, None)
            if cmd is not None:
                result[kind] = " ".join(cmd.command)
        return result
    except Exception:
        return {}


def _detect_entrypoints(project_root: Path) -> list[str]:
    """Return likely entrypoint paths relative to project root."""
    candidates = [
        "src/",
        "app.py",
        "main.py",
        "index.py",
        "server.py",
        "cmd/",
        "main.go",
        "src/main.rs",
        "src/lib.rs",
        "index.ts",
        "src/index.ts",
    ]
    found = []
    for c in candidates:
        p = project_root / c
        if p.exists():
            found.append(c.rstrip("/"))
    return found[:10]


def _detect_test_dirs(project_root: Path) -> list[str]:
    """Return likely test directory names relative to project root."""
    candidates = ["tests", "test", "__tests__", "spec", "specs", "src/test", "src/tests"]
    found = []
    for c in candidates:
        if (project_root / c).is_dir():
            found.append(c)
    return found[:5]


def _high_signal_files(project_root: Path) -> list[str]:
    """Return high-signal file paths relative to project root (no content)."""
    found: list[str] = []
    seen: set[str] = set()
    for glob in _HIGH_SIGNAL_GLOBS:
        for p in sorted(project_root.glob(glob)):
            if not p.is_file():
                continue
            rel = str(p.relative_to(project_root))
            # Respect root boundary
            if ".." in rel:
                continue
            if rel not in seen:
                seen.add(rel)
                found.append(rel)
            if len(found) >= _MAX_HIGH_SIGNAL_FILES:
                break
        if len(found) >= _MAX_HIGH_SIGNAL_FILES:
            break
    return found


def _pinned_files(project_root: Path) -> list[str]:
    try:
        from safecode.memory.facade import MemoryFacade
        facade = MemoryFacade(project_root)
        return list(facade.read_pinned_files())[:10]
    except Exception:
        return []


def _current_task_info(project_root: Path) -> dict[str, Any]:
    try:
        from safecode.task.store import TaskStore
        from safecode.context.redactor import redact_secrets
        store = TaskStore(project_root)
        current_id = store.current_id()
        if not current_id:
            return {}
        state = store.load(current_id)
        if state is None:
            return {}
        return {
            "task_id": state.task_id,
            "goal": redact_secrets(state.goal),
            "status": state.status,
        }
    except Exception:
        return {}


def _recent_failure_summaries(project_root: Path) -> list[str]:
    try:
        from safecode.memory.facade import MemoryFacade
        facade = MemoryFacade(project_root)
        failures = facade.read_recent_failures(limit=_MAX_RECENT_FAILURES)
        return [
            redact_secrets(f"{e.command} (exit {e.exit_code}): {e.tail_summary[:80]}")
            for e in failures
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_project_overview(project_root: Path) -> ProjectOverview:
    """Build a bounded, deterministic project overview from local signals.

    Context is bounded to _MAX_OVERVIEW_BYTES. Signals that would exceed the
    budget are listed in `skipped_signals` for transparency.
    """
    root = project_root.resolve()
    skipped: list[str] = []

    stack = _detect_stack(root)
    branch = _git_branch(root)
    dirty = _git_dirty(root)
    commits = _git_recent_commits(root)
    profile_cmds = _profile_commands(root)
    entrypoints = _detect_entrypoints(root)
    test_dirs = _detect_test_dirs(root)
    high_signal = _high_signal_files(root)
    pinned = _pinned_files(root)
    task_info = _current_task_info(root)
    failures = _recent_failure_summaries(root)

    overview = ProjectOverview(
        project_root=str(root),
        stack=stack,
        git_branch=branch,
        git_dirty=dirty,
        recent_commits=commits,
        profile_commands=profile_cmds,
        entrypoints=entrypoints,
        test_dirs=test_dirs,
        high_signal_files=high_signal,
        pinned_files=pinned,
        current_task=task_info,
        recent_failures=failures,
        skipped_signals=skipped,
    )

    # Budget check: if rendered text exceeds the limit, trim signals and note them
    rendered = overview.render_text()
    if len(rendered.encode("utf-8")) > _MAX_OVERVIEW_BYTES:
        # Trim in reverse priority order
        trimmed_failures: list[str] = []
        trimmed_commits: list[str] = commits[:2]
        trimmed_high: list[str] = high_signal[:10]
        skipped = ["some recent_commits", "some high_signal_files", "some recent_failures"]
        overview = ProjectOverview(
            project_root=str(root),
            stack=stack,
            git_branch=branch,
            git_dirty=dirty,
            recent_commits=trimmed_commits,
            profile_commands=profile_cmds,
            entrypoints=entrypoints,
            test_dirs=test_dirs,
            high_signal_files=trimmed_high,
            pinned_files=pinned,
            current_task=task_info,
            recent_failures=trimmed_failures,
            skipped_signals=skipped,
        )

    return overview
