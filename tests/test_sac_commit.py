"""Tests for experimental sac commit (v4.5.0)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.cli import app
from safecode.git import local as git_local
from safecode.task.store import TaskStore

runner = CliRunner()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "sac@example.test")
    _git(tmp_path, "config", "user.name", "SafeCode Test")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _task_with_checkpoint(root: Path, goal: str, files: list[str]):
    store = TaskStore(root)
    task = store.create(goal)
    checkpoint_id = "2026-01-01T00-00-00_cp"
    checkpoint_dir = root / ".sac" / "checkpoints" / checkpoint_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    metadata = CheckpointMetadata(
        checkpoint_id=checkpoint_id,
        task=goal,
        patch_id="patch-1",
        created_at="2026-01-01T00:00:00Z",
        file_operations=[
            CheckpointFileOperation(path=file, operation="update", existed_before=True, backup_path=None)
            for file in files
        ],
    )
    (checkpoint_dir / "metadata.json").write_text(json.dumps(metadata.model_dump()), encoding="utf-8")
    updated = task.model_copy(update={"status": "applied", "audit_trace_ids": [checkpoint_id]})
    store.save(updated)
    return updated


class TestSacCommit:
    def test_non_git_repo_refuses(self, tmp_path):
        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["commit", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["status"] == "error"

    def test_stages_only_task_files_and_commits_deterministic_message(self, tmp_path):
        root = _repo(tmp_path)
        _task_with_checkpoint(root, "Fix login token handling", ["tracked.txt"])
        (root / "tracked.txt").write_text("task change\n", encoding="utf-8")
        (root / "unrelated.txt").write_text("leave me alone\n", encoding="utf-8")

        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["commit", "--json"])

        assert result.exit_code == 0, result.output
        assert "tracked.txt" in _git(root, "show", "--name-only", "--format=", "HEAD")
        assert "unrelated.txt" not in _git(root, "show", "--name-only", "--format=", "HEAD")
        message = _git(root, "log", "-1", "--format=%B")
        assert message.startswith("Fix login token handling\n\nTask: ")
        assert (root / "unrelated.txt").exists()

    def test_allow_unrelated_changes_does_not_stage_unrelated(self, tmp_path):
        root = _repo(tmp_path)
        _task_with_checkpoint(root, "Update owned file", ["owned.txt"])
        (root / "owned.txt").write_text("owned\n", encoding="utf-8")
        (root / "README.md").write_text("dirty unrelated\n", encoding="utf-8")

        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["commit", "--allow-unrelated-changes", "--json"])

        assert result.exit_code == 0, result.output
        assert "owned.txt" in _git(root, "show", "--name-only", "--format=", "HEAD")
        assert "README.md" not in _git(root, "show", "--name-only", "--format=", "HEAD")

    def test_git_helpers_use_argv_and_shell_false(self, tmp_path):
        calls: list[dict] = []

        def fake_run(args, **kwargs):
            calls.append({"args": args, **kwargs})
            return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")

        with patch("safecode.git.local.subprocess.run", side_effect=fake_run):
            assert git_local.is_git_repo(tmp_path)

        assert calls
        assert calls[0]["args"] == ["git", "rev-parse", "--is-inside-work-tree"]
        assert calls[0]["shell"] is False

