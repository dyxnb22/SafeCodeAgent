"""Read-only sandboxed PR workspace checkout (v2.2.2-T2)."""

from __future__ import annotations

import io
import os
import re
import shutil
import stat
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from uuid import uuid4

from safecode.config import SafeCodeConfig
from safecode.sandbox.execution import SandboxExecutionGate, SandboxExecutionProposal
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.filesystem import FilesystemBoundary

_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DEFAULT_MAX_WORKSPACE_BYTES = 50 * 1024 * 1024


class PRWorkspaceError(Exception):
    """Base PR workspace error."""


class PRWorkspaceSecurityError(PRWorkspaceError):
    """Raised when checkout content violates sandbox boundaries."""


class PRWorkspaceBoundsError(PRWorkspaceError):
    """Raised when checkout exceeds configured size bounds."""


class PRWorkspaceMutationError(PRWorkspaceError):
    """Raised when a direct workspace mutation is attempted."""


class PRWorkspaceCleanupError(PRWorkspaceError):
    """Raised when workspace cleanup fails."""


class GitArchivePort(Protocol):
    """Archive a pinned commit into a destination directory."""

    def archive_commit(self, source_repo: Path, commit_sha: str, dest: Path) -> None:
        """Materialize commit contents under dest."""


@dataclass(frozen=True)
class PRWorkspaceSpec:
    """Inputs for a pinned read-only workspace checkout."""

    commit_sha: str
    source_repo: Path
    workspace_id: str | None = None


@dataclass(frozen=True)
class PRWorkspaceCheckout:
    """Active read-only workspace pinned to an immutable commit SHA."""

    workspace_id: str
    root: Path
    commit_sha: str
    read_only: bool = True


@dataclass(frozen=True)
class PRWorkspaceCleanupOutcome:
    """Audited cleanup result for an ephemeral workspace."""

    workspace_id: str
    removed: bool
    error: str | None = None


ArchiveFn = Callable[[Path, str, Path], None]
CleanupFn = Callable[[Path], None]


class PRWorkspaceManager:
    """Create, validate, and dispose read-only PR workspaces under a sandbox root."""

    def __init__(
        self,
        sandbox_root: Path,
        *,
        max_workspace_bytes: int = DEFAULT_MAX_WORKSPACE_BYTES,
        archive_fn: ArchiveFn | None = None,
        cleanup_fn: CleanupFn | None = None,
    ) -> None:
        self.sandbox_root = sandbox_root.resolve()
        self.max_workspace_bytes = max_workspace_bytes
        self._archive_fn = archive_fn or _default_git_archive
        self._cleanup_fn = cleanup_fn or _default_cleanup

    def checkout(self, spec: PRWorkspaceSpec) -> PRWorkspaceCheckout:
        commit_sha = _validate_commit_sha(spec.commit_sha)
        source_repo = spec.source_repo.resolve()
        if not source_repo.is_dir():
            raise PRWorkspaceError(f"source repository not found: {source_repo}")

        workspace_id = spec.workspace_id or uuid4().hex
        workspace_root = self._workspace_path(workspace_id)
        if workspace_root.exists():
            raise PRWorkspaceError(f"workspace already exists: {workspace_id}")

        workspace_root.mkdir(parents=True, exist_ok=False)
        try:
            self._archive_fn(source_repo, commit_sha, workspace_root)
            _validate_tree(workspace_root, self.sandbox_root, self.max_workspace_bytes)
            _make_readonly(workspace_root)
        except Exception:
            _safe_rmtree(workspace_root)
            raise

        return PRWorkspaceCheckout(
            workspace_id=workspace_id,
            root=workspace_root,
            commit_sha=commit_sha,
            read_only=True,
        )

    def read_text(self, checkout: PRWorkspaceCheckout, relative_path: str) -> str:
        target = self.resolve_path(checkout, relative_path)
        if not target.is_file() or target.is_symlink():
            raise PRWorkspaceError(f"not a readable file: {relative_path}")
        return target.read_text(encoding="utf-8")

    def resolve_path(self, checkout: PRWorkspaceCheckout, relative_path: str) -> Path:
        boundary = FilesystemBoundary(checkout.root)
        candidate = (checkout.root / relative_path).resolve()
        return boundary.validate(candidate)

    def propose_mutation(
        self,
        checkout: PRWorkspaceCheckout,
        *,
        project_root: Path,
        command: list[str],
        purpose: str = "pr_workspace_mutation",
    ) -> SandboxExecutionProposal:
        """Route filesystem mutations through the sandbox proposal pipeline."""
        if not command:
            raise PRWorkspaceMutationError("mutation command must be non-empty")
        config = SafeCodeConfig.load(project_root)
        plan = SandboxAdapterFactory(project_root, config).create_plan(
            command=list(command),
            purpose=purpose,
            allow_network=False,
            readonly_filesystem=False,
            writable_paths=[checkout.root],
        )
        gate = SandboxExecutionGate(project_root, config)
        return gate.propose(plan, purpose)

    def write_text(
        self,
        checkout: PRWorkspaceCheckout,
        relative_path: str,
        content: str,
    ) -> None:
        """Direct writes are forbidden; mutations require sandbox proposals."""
        _ = checkout, relative_path, content
        raise PRWorkspaceMutationError(
            "direct workspace writes are forbidden; use propose_mutation()"
        )

    def cleanup(self, checkout: PRWorkspaceCheckout) -> PRWorkspaceCleanupOutcome:
        if not checkout.root.exists():
            return PRWorkspaceCleanupOutcome(
                workspace_id=checkout.workspace_id,
                removed=True,
            )
        try:
            self._cleanup_fn(checkout.root)
        except OSError as exc:
            raise PRWorkspaceCleanupError(
                f"failed to remove workspace {checkout.workspace_id}: {exc}"
            ) from exc
        removed = not checkout.root.exists()
        if not removed:
            raise PRWorkspaceCleanupError(
                f"workspace still present after cleanup: {checkout.workspace_id}"
            )
        return PRWorkspaceCleanupOutcome(
            workspace_id=checkout.workspace_id,
            removed=True,
        )

    def _workspace_path(self, workspace_id: str) -> Path:
        root = (self.sandbox_root / workspace_id).resolve()
        if root != self.sandbox_root and self.sandbox_root not in root.parents:
            raise PRWorkspaceSecurityError(f"workspace path escapes sandbox root: {workspace_id}")
        return root


def _default_cleanup(path: Path) -> None:
    _restore_writable(path)
    shutil.rmtree(path)


def _restore_writable(root: Path) -> None:
    for path in sorted([root, *root.rglob("*")], reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IWUSR)


def _safe_rmtree(path: Path) -> None:
    try:
        if path.exists():
            _restore_writable(path)
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def _validate_commit_sha(commit_sha: str) -> str:
    normalized = commit_sha.strip()
    if not _COMMIT_SHA_RE.fullmatch(normalized):
        raise PRWorkspaceSecurityError(
            "commit SHA must be a pinned 40-character hex digest; refs are not allowed"
        )
    return normalized.lower()


def _validate_tree(workspace_root: Path, sandbox_root: Path, max_workspace_bytes: int) -> None:
    total_bytes = 0
    if (workspace_root / ".gitmodules").exists():
        raise PRWorkspaceSecurityError("submodule metadata is not allowed in PR workspaces")

    for path in workspace_root.rglob("*"):
        if path.is_symlink():
            target = path.resolve()
            if sandbox_root not in target.parents and target != sandbox_root:
                raise PRWorkspaceSecurityError(f"symlink escapes sandbox root: {path}")
            if workspace_root not in target.parents and target != workspace_root:
                raise PRWorkspaceSecurityError(f"symlink escapes workspace root: {path}")
            continue

        if path.is_file():
            total_bytes += path.stat().st_size
            if total_bytes > max_workspace_bytes:
                raise PRWorkspaceBoundsError(
                    f"workspace exceeds max size of {max_workspace_bytes} bytes"
                )

        try:
            path.relative_to(workspace_root)
        except ValueError as exc:
            raise PRWorkspaceSecurityError(f"path escapes workspace root: {path}") from exc


def _make_readonly(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
    if not root.is_symlink():
        root.chmod(root.stat().st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def _default_git_archive(source_repo: Path, commit_sha: str, dest: Path) -> None:
    object_type = subprocess.run(
        ["git", "cat-file", "-t", commit_sha],
        cwd=source_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if object_type.returncode != 0 or object_type.stdout.strip() not in {"commit", "tag"}:
        raise PRWorkspaceSecurityError(f"commit SHA not found in repository: {commit_sha}")

    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit_sha],
        cwd=source_repo,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        stderr = archive.stderr.decode("utf-8", errors="replace")
        raise PRWorkspaceError(f"git archive failed for {commit_sha}: {stderr.strip()}")

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            for member in tar.getmembers():
                member_path = (dest / member.name).resolve()
                if dest not in member_path.parents and member_path != dest:
                    raise PRWorkspaceSecurityError(
                        f"archive member escapes workspace root: {member.name}"
                    )
            tar.extractall(dest)


def materialize_tree(source: Path, dest: Path) -> None:
    """Copy a fixture tree into a workspace root (test helper)."""
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        target = dest / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_symlink():
            target.symlink_to(os.readlink(path))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
