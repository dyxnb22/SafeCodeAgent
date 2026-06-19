"""Tests for sandboxed PR workspace checkout (v2.2.2-T2)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from safecode.enterprise.sandbox.pr_workspace import (
    PRWorkspaceBoundsError,
    PRWorkspaceCleanupError,
    PRWorkspaceManager,
    PRWorkspaceMutationError,
    PRWorkspaceSecurityError,
    PRWorkspaceSpec,
    materialize_tree,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path, *, content: str = "print('hello')\n") -> str:
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return _git(repo, "rev-parse", "HEAD")


def _archive_from_repo(source_repo: Path, commit_sha: str, dest: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit_sha],
        cwd=source_repo,
        capture_output=True,
        check=False,
    )
    assert archive.returncode == 0
    import io
    import tarfile

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)


def test_checkout_is_read_only_and_cleans_up(tmp_path: Path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    commit_sha = _init_repo(source_repo)
    sandbox_root = tmp_path / "sandboxes"
    manager = PRWorkspaceManager(
        sandbox_root,
        archive_fn=_archive_from_repo,
    )

    checkout = manager.checkout(
        PRWorkspaceSpec(commit_sha=commit_sha, source_repo=source_repo)
    )
    assert checkout.read_only is True
    assert checkout.commit_sha == commit_sha.lower()
    assert manager.read_text(checkout, "app.py") == "print('hello')\n"
    assert not os.access(checkout.root / "app.py", os.W_OK)

    outcome = manager.cleanup(checkout)
    assert outcome.removed is True
    assert not checkout.root.exists()


def test_direct_write_rejected(tmp_path: Path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    commit_sha = _init_repo(source_repo)
    manager = PRWorkspaceManager(tmp_path / "sandboxes", archive_fn=_archive_from_repo)
    checkout = manager.checkout(
        PRWorkspaceSpec(commit_sha=commit_sha, source_repo=source_repo)
    )

    with pytest.raises(PRWorkspaceMutationError, match="direct workspace writes"):
        manager.write_text(checkout, "app.py", "changed")


def _stub_source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source-stub"
    repo.mkdir()
    return repo


def test_propose_mutation_uses_sandbox_pipeline(tmp_path: Path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    commit_sha = _init_repo(source_repo)
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    sandbox_root = project_root / "sandboxes"

    manager = PRWorkspaceManager(sandbox_root, archive_fn=_archive_from_repo)
    checkout = manager.checkout(
        PRWorkspaceSpec(commit_sha=commit_sha, source_repo=source_repo)
    )

    proposal = manager.propose_mutation(
        checkout,
        project_root=project_root,
        command=["echo", "mutate"],
        purpose="test_mutation",
    )
    assert proposal.readonly_filesystem is False
    assert str(checkout.root) in proposal.writable_paths
    assert proposal.command == ["echo", "mutate"]


def test_ref_substitution_rejected(tmp_path: Path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    _init_repo(source_repo)
    manager = PRWorkspaceManager(tmp_path / "sandboxes", archive_fn=_archive_from_repo)

    with pytest.raises(PRWorkspaceSecurityError, match="refs are not allowed"):
        manager.checkout(
            PRWorkspaceSpec(commit_sha="main", source_repo=source_repo)
        )
    with pytest.raises(PRWorkspaceSecurityError, match="refs are not allowed"):
        manager.checkout(
            PRWorkspaceSpec(commit_sha="HEAD", source_repo=source_repo)
        )


def test_symlink_escape_rejected(tmp_path: Path):
    sandbox_root = tmp_path / "sandboxes"
    sandbox_root.mkdir()
    secret = sandbox_root / "outside" / "secret.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text("secret", encoding="utf-8")

    def archive_with_symlink(_source: Path, _sha: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "app.py").write_text("ok", encoding="utf-8")
        (dest / "escape").symlink_to(secret)

    stub_repo = _stub_source_repo(tmp_path)
    manager = PRWorkspaceManager(
        sandbox_root,
        archive_fn=archive_with_symlink,
    )
    with pytest.raises(PRWorkspaceSecurityError, match="symlink escapes workspace root"):
        manager.checkout(
            PRWorkspaceSpec(
                commit_sha="a" * 40,
                source_repo=stub_repo,
            )
        )


def test_submodule_escape_rejected(tmp_path: Path):
    def archive_with_submodules(_source: Path, _sha: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".gitmodules").write_text("[submodule \"x\"]\n", encoding="utf-8")

    stub_repo = _stub_source_repo(tmp_path)
    manager = PRWorkspaceManager(
        tmp_path / "sandboxes",
        archive_fn=archive_with_submodules,
    )
    with pytest.raises(PRWorkspaceSecurityError, match="submodule metadata"):
        manager.checkout(
            PRWorkspaceSpec(
                commit_sha="b" * 40,
                source_repo=stub_repo,
            )
        )


def test_oversize_workspace_rejected(tmp_path: Path):
    def archive_oversize(_source: Path, _sha: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "large.bin").write_bytes(b"x" * 2048)

    stub_repo = _stub_source_repo(tmp_path)
    manager = PRWorkspaceManager(
        tmp_path / "sandboxes",
        max_workspace_bytes=1024,
        archive_fn=archive_oversize,
    )
    with pytest.raises(PRWorkspaceBoundsError, match="exceeds max size"):
        manager.checkout(
            PRWorkspaceSpec(
                commit_sha="c" * 40,
                source_repo=stub_repo,
            )
        )


def test_cleanup_failure_fail_closed(tmp_path: Path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    commit_sha = _init_repo(source_repo)

    def failing_cleanup(_path: Path) -> None:
        raise OSError("permission denied")

    manager = PRWorkspaceManager(
        tmp_path / "sandboxes",
        archive_fn=_archive_from_repo,
        cleanup_fn=failing_cleanup,
    )
    checkout = manager.checkout(
        PRWorkspaceSpec(commit_sha=commit_sha, source_repo=source_repo)
    )
    assert checkout.root.exists()

    with pytest.raises(PRWorkspaceCleanupError, match="failed to remove workspace"):
        manager.cleanup(checkout)


def test_path_escape_rejected_on_read(tmp_path: Path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    commit_sha = _init_repo(source_repo)
    manager = PRWorkspaceManager(tmp_path / "sandboxes", archive_fn=_archive_from_repo)
    checkout = manager.checkout(
        PRWorkspaceSpec(commit_sha=commit_sha, source_repo=source_repo)
    )

    with pytest.raises(PermissionError, match="escapes project root"):
        manager.read_text(checkout, "../outside.txt")


def test_materialize_tree_helper_for_fixtures(tmp_path: Path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "README.md").write_text("# fixture\n", encoding="utf-8")
    dest = tmp_path / "dest"
    materialize_tree(fixture, dest)
    assert (dest / "README.md").read_text(encoding="utf-8") == "# fixture\n"
