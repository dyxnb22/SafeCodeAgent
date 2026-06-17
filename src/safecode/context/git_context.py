"""Git-aware context collection for SafeCode Agent (v5.3.0).

Injects recent git activity into agent sessions so the model knows:
- What changed recently (last 10 commits)
- Which files changed since the branch diverged from main/master
- Which files are high-churn (frequently modified in last 30 days)

All git commands run with shell=False, timeout=10s, and fail silently.
The module is a no-op when git is unavailable or the project is not a git repo.
"""

from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path


_GIT_TIMEOUT = 10  # seconds per git subprocess call
_MAX_COMMITS = 10
_MAX_CONTEXT_CHARS = 2000
_HIGH_CHURN_DAYS = 30
_HIGH_CHURN_LIMIT = 15


@dataclass
class CommitInfo:
    """Summary of one recent commit."""
    hash: str
    subject: str
    author: str
    files_changed: list[str] = field(default_factory=list)


@dataclass
class GitContext:
    """Bounded git activity context block."""
    recent_commits: list[CommitInfo] = field(default_factory=list)
    branch_diff_files: list[str] = field(default_factory=list)  # files changed vs main/master
    high_churn_files: list[str] = field(default_factory=list)   # frequently modified files
    error: str | None = None  # set when git is unavailable or failed

    def is_empty(self) -> bool:
        return not self.recent_commits and not self.branch_diff_files and not self.high_churn_files

    def to_context_block(self) -> str:
        """Render as a bounded context string (≤ _MAX_CONTEXT_CHARS)."""
        if self.error or self.is_empty():
            return ""

        lines: list[str] = ["## Git Context (recent activity)"]

        if self.recent_commits:
            lines.append(f"\nRecent commits (last {len(self.recent_commits)}):")
            for commit in self.recent_commits:
                files_str = ", ".join(commit.files_changed[:5])
                if len(commit.files_changed) > 5:
                    files_str += f" (+{len(commit.files_changed) - 5} more)"
                lines.append(f"  {commit.hash[:8]}  {commit.subject}  [{files_str}]")

        if self.branch_diff_files:
            lines.append(f"\nFiles changed since main/master ({len(self.branch_diff_files)}):")
            for f in self.branch_diff_files[:20]:
                lines.append(f"  {f}")
            if len(self.branch_diff_files) > 20:
                lines.append(f"  ... and {len(self.branch_diff_files) - 20} more")

        if self.high_churn_files:
            lines.append(f"\nHigh-churn files (last {_HIGH_CHURN_DAYS} days):")
            for f in self.high_churn_files[:10]:
                lines.append(f"  {f}")

        text = "\n".join(lines)
        return text[:_MAX_CONTEXT_CHARS]


class GitContextCollector:
    """Collect bounded git activity context for one project root."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._git = shutil.which("git")

    def _run(self, args: list[str]) -> str:
        """Run a git subcommand; return stdout or empty string on failure."""
        if not self._git:
            return ""
        try:
            result = subprocess.run(
                [self._git, *args],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
                shell=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            pass
        return ""

    def _is_git_repo(self) -> bool:
        return bool(self._run(["rev-parse", "--git-dir"]))

    def _collect_recent_commits(self) -> list[CommitInfo]:
        """Return last N commits with hash, subject, author, files."""
        commits: list[CommitInfo] = []
        # Get hash, author, subject
        log_out = self._run([
            "log", f"-{_MAX_COMMITS}",
            "--format=%H|%ae|%s",
            "--no-merges",
        ])
        if not log_out:
            return commits

        hashes: list[tuple[str, str, str]] = []
        for line in log_out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                hashes.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))

        for hash_, author, subject in hashes:
            # Get files changed in this commit
            files_out = self._run(["diff-tree", "--no-commit-id", "-r", "--name-only", hash_])
            files = [f.strip() for f in files_out.splitlines() if f.strip()][:10]
            commits.append(CommitInfo(hash=hash_, subject=subject[:80], author=author, files_changed=files))

        return commits

    def _collect_branch_diff_files(self) -> list[str]:
        """Return files changed since this branch diverged from main/master."""
        # Try origin/main then origin/master then main then master
        for base in ("origin/main", "origin/master", "main", "master"):
            out = self._run(["diff", "--name-only", f"{base}...HEAD"])
            if out:
                return [f.strip() for f in out.splitlines() if f.strip()]
        return []

    def _collect_high_churn_files(self) -> list[str]:
        """Return files with the most commits in the last _HIGH_CHURN_DAYS days."""
        out = self._run([
            "log",
            f"--since={_HIGH_CHURN_DAYS}.days.ago",
            "--name-only",
            "--format=",
        ])
        if not out:
            return []
        counts: dict[str, int] = {}
        for line in out.splitlines():
            f = line.strip()
            if f:
                counts[f] = counts.get(f, 0) + 1
        sorted_files = sorted(counts, key=lambda k: counts[k], reverse=True)
        return sorted_files[:_HIGH_CHURN_LIMIT]

    def collect(self) -> GitContext:
        """Collect bounded git context; returns GitContext with error set if unavailable."""
        if not self._git:
            return GitContext(error="git not found")
        if not self._is_git_repo():
            return GitContext(error="not a git repository")
        try:
            return GitContext(
                recent_commits=self._collect_recent_commits(),
                branch_diff_files=self._collect_branch_diff_files(),
                high_churn_files=self._collect_high_churn_files(),
            )
        except Exception as exc:
            return GitContext(error=f"git context collection failed: {type(exc).__name__}")


def collect_git_context(project_root: Path) -> GitContext:
    """Convenience function: collect git context for a project root."""
    return GitContextCollector(project_root).collect()


# ---------------------------------------------------------------------------
# v6.8.1 — per-file git context
# ---------------------------------------------------------------------------

_PER_FILE_MAX_LOG_LINES = 5
_PER_FILE_MAX_DIFF_CHARS = 600
_PER_FILE_TOTAL_CAP = 2000
_PER_FILE_TOP_N = 5


def collect_per_file_git_context(project_root: Path, rel_paths: list[str]) -> str:
    """Return a compact git log + diff summary for the top-N selected files.

    Runs ``git log -5 --oneline <file>`` and ``git diff HEAD~1 -- <file>``
    for each of the first ``_PER_FILE_TOP_N`` files. All subprocess calls use
    ``shell=False``, timeout=8s, and fail silently. Output is capped at
    ``_PER_FILE_TOTAL_CAP`` chars and passed through ``redact_secrets()``.

    Returns an empty string when git is not available or no output is produced.
    """
    if not shutil.which("git"):
        return ""
    if not rel_paths:
        return ""

    from safecode.context.redactor import redact_secrets

    sections: list[str] = []
    total_chars = 0

    for rel in rel_paths[:_PER_FILE_TOP_N]:
        if total_chars >= _PER_FILE_TOTAL_CAP:
            break

        file_lines: list[str] = [f"### {rel}"]

        # git log
        try:
            log_result = subprocess.run(
                ["git", "log", f"-{_PER_FILE_MAX_LOG_LINES}", "--oneline", "--", rel],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                shell=False,
                timeout=8,
            )
            log_out = log_result.stdout.strip()
            if log_out:
                file_lines.append("Recent commits:")
                file_lines.extend(f"  {ln}" for ln in log_out.splitlines()[:_PER_FILE_MAX_LOG_LINES])
        except Exception:
            pass

        # git diff HEAD~1
        try:
            diff_result = subprocess.run(
                ["git", "diff", "HEAD~1", "--", rel],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                shell=False,
                timeout=8,
            )
            diff_out = diff_result.stdout.strip()
            if diff_out:
                diff_trimmed = diff_out[:_PER_FILE_MAX_DIFF_CHARS]
                if len(diff_out) > _PER_FILE_MAX_DIFF_CHARS:
                    diff_trimmed += "\n... (truncated)"
                file_lines.append("Diff vs HEAD~1:")
                file_lines.append(diff_trimmed)
        except Exception:
            pass

        if len(file_lines) > 1:  # has more than just the header
            block = redact_secrets("\n".join(file_lines))
            sections.append(block)
            total_chars += len(block)

    if not sections:
        return ""
    body = "\n\n".join(sections)
    if len(body) > _PER_FILE_TOTAL_CAP:
        body = body[:_PER_FILE_TOTAL_CAP] + "\n... (truncated)"
    return "## Per-file git context\n" + body
