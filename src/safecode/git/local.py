"""Argv-only local Git helpers for experimental v4.5 delivery commands."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.checkpoint.models import CheckpointMetadata
from safecode.context.redactor import redact_secrets
from safecode.patch.models import PatchProposal
from safecode.task.state import TaskState
from safecode.task.store import TaskStore
from safecode.utils.time import utc_now_iso


class GitError(RuntimeError):
    """Raised when a local git command fails closed."""


@dataclass(frozen=True)
class DirtyTreeResult:
    """Result from the dirty-tree guard."""

    ok: bool
    unrelated_files: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        if self.ok:
            return "working tree ok"
        joined = ", ".join(self.unrelated_files)
        return f"Unrelated uncommitted changes detected: {joined}. Commit, stash, or rerun with --allow-unrelated-changes."


_BAD_BRANCH_CHARS = re.compile(r"[\s;&|$`<>!(){}]")


def _run(project_root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git with argv only and shell disabled."""
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    if check and completed.returncode != 0:
        err = redact_secrets((completed.stderr or completed.stdout or "git command failed").strip())
        raise GitError(err)
    return completed


def is_git_repo(project_root: Path) -> bool:
    return _run(project_root, ["rev-parse", "--is-inside-work-tree"], check=False).stdout.strip() == "true"


def current_branch(project_root: Path) -> str:
    return _run(project_root, ["branch", "--show-current"]).stdout.strip()


def status_porcelain(project_root: Path) -> tuple[str, ...]:
    output = _run(project_root, ["status", "--porcelain=v1", "--untracked-files=all"]).stdout
    return tuple(line for line in output.splitlines() if line.strip())


def _status_path(line: str) -> str:
    raw = line[3:] if len(line) > 3 else ""
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1]
    return raw.strip().strip('"')


def changed_files(project_root: Path) -> tuple[str, ...]:
    return tuple(sorted({_status_path(line) for line in status_porcelain(project_root) if _status_path(line)}))


def staged_files(project_root: Path) -> tuple[str, ...]:
    output = _run(project_root, ["diff", "--cached", "--name-only"]).stdout
    return tuple(sorted(line for line in output.splitlines() if line.strip()))


def add_files(project_root: Path, files: list[str]) -> None:
    if files:
        _run(project_root, ["add", "--", *sorted(files)])


def commit(project_root: Path, message: str) -> str:
    completed = _run(project_root, ["commit", "-m", message])
    return completed.stdout.strip()


def diff_name_only(project_root: Path) -> tuple[str, ...]:
    output = _run(project_root, ["diff", "--name-only", "HEAD", "--"]).stdout
    return tuple(sorted(line for line in output.splitlines() if line.strip()))


def diff_for_files(project_root: Path, files: list[str]) -> str:
    if not files:
        return ""
    return _run(project_root, ["diff", "HEAD", "--", *sorted(files)]).stdout


def branch_exists(project_root: Path, name: str) -> bool:
    return _run(project_root, ["show-ref", "--verify", "--quiet", f"refs/heads/{name}"], check=False).returncode == 0


def validate_branch_name(project_root: Path, name: str) -> None:
    if not name or not name.strip():
        raise GitError("Branch name must be non-empty.")
    if name.startswith("-") or _BAD_BRANCH_CHARS.search(name):
        raise GitError("Branch name contains unsafe characters.")
    forbidden = ("..", "~", "^", ":", "?", "*", "[", "\\")
    if any(part in name for part in forbidden):
        raise GitError("Branch name is not a valid git branch name.")
    checked = _run(project_root, ["check-ref-format", "--branch", name], check=False)
    if checked.returncode != 0:
        raise GitError("Branch name is not a valid git branch name.")


def create_branch(project_root: Path, name: str) -> None:
    validate_branch_name(project_root, name)
    if branch_exists(project_root, name):
        raise GitError(f"Branch already exists: {name}")
    _run(project_root, ["branch", name])


def switch_branch(project_root: Path, name: str) -> None:
    validate_branch_name(project_root, name)
    _run(project_root, ["switch", name])


def create_and_switch_branch(project_root: Path, name: str) -> None:
    create_branch(project_root, name)
    switch_branch(project_root, name)


def _checkpoint_metadata_path(project_root: Path, checkpoint_id: str) -> Path:
    return project_root / ".sac" / "checkpoints" / checkpoint_id / "metadata.json"


def load_checkpoint(project_root: Path, checkpoint_id: str) -> CheckpointMetadata | None:
    path = _checkpoint_metadata_path(project_root, checkpoint_id)
    if not path.is_file():
        return None
    try:
        return CheckpointMetadata(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def pending_patch(project_root: Path) -> PatchProposal | None:
    path = project_root / ".sac" / "pending_patch.json"
    if not path.is_file():
        return None
    try:
        return PatchProposal(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def current_task(project_root: Path) -> TaskState | None:
    store = TaskStore(project_root)
    task_id = store.current_id()
    return store.load(task_id) if task_id else None


def task_files(project_root: Path, task: TaskState, *, include_pending: bool = False) -> tuple[str, ...]:
    files: set[str] = set()
    for trace_id in task.audit_trace_ids:
        checkpoint = load_checkpoint(project_root, trace_id)
        if checkpoint is not None:
            files.update(operation.path for operation in checkpoint.file_operations)
    for iteration in task.iterations:
        if iteration.audit_trace_id:
            checkpoint = load_checkpoint(project_root, iteration.audit_trace_id)
            if checkpoint is not None:
                files.update(operation.path for operation in checkpoint.file_operations)
    for event in AuditLogger(project_root).read_by_task_id(task.task_id, limit=500):
        files.update(event.files)
    if include_pending:
        patch = pending_patch(project_root)
        if patch is not None:
            files.update(block.file_path.as_posix() for block in patch.blocks)
    return tuple(sorted(f for f in files if f))


def dirty_tree_guard(project_root: Path, allowed_files: set[str]) -> DirtyTreeResult:
    allowed = {Path(path).as_posix().strip("/") for path in allowed_files if path}
    touched_dirs = {Path(path).parent.as_posix() for path in allowed if Path(path).parent.as_posix() != "."}
    unrelated: set[str] = set()
    for line in status_porcelain(project_root):
        path = _status_path(line)
        if not path:
            continue
        code = line[:2]
        normalized = Path(path).as_posix()
        if normalized in allowed:
            continue
        if code == "??":
            if any(normalized == d or normalized.startswith(f"{d}/") for d in touched_dirs):
                unrelated.add(normalized)
            continue
        unrelated.add(normalized)
    return DirtyTreeResult(ok=not unrelated, unrelated_files=tuple(sorted(unrelated)))


def audit_dirty_refusal(project_root: Path, task_id: str | None, files: tuple[str, ...], command: str) -> None:
    try:
        AuditLogger(project_root).write(
            AuditEvent(
                type="dirty_tree_refused",
                timestamp=utc_now_iso(),
                status="error",
                files=list(files),
                message=f"{command} refused due to unrelated changes",
            ),
            task_id=task_id,
        )
    except Exception:
        pass


def commit_for_files(project_root: Path, files: list[str]) -> str | None:
    if not files:
        return None
    output = _run(project_root, ["log", "-n", "50", "--format=%H", "--", *sorted(files)], check=False).stdout
    for sha in [line.strip() for line in output.splitlines() if line.strip()]:
        changed = _run(project_root, ["diff-tree", "--no-commit-id", "--name-only", "-r", sha], check=False).stdout
        changed_set = {line.strip() for line in changed.splitlines() if line.strip()}
        if set(files).issubset(changed_set):
            return sha
    return None


def commit_contains_files_or_checkpoint(project_root: Path, checkpoint: CheckpointMetadata) -> str | None:
    files = [operation.path for operation in checkpoint.file_operations]
    return commit_for_files(project_root, files)

