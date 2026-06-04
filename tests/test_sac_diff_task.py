"""Tests for experimental sac diff --task (v4.5.2)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.cli import app
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.task.store import TaskStore

runner = CliRunner()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "sac@example.test")
    _git(tmp_path, "config", "user.name", "SafeCode Test")
    (tmp_path / "app.py").write_text("print('base')\n", encoding="utf-8")
    (tmp_path / "config.py").write_text("api_key = \"old\"\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py", "config.py")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _task_with_checkpoint(root: Path, files: list[str]):
    state = TaskStore(root).create("Inspect task diff")
    checkpoint_id = "2026-01-01T00-00-00_cp"
    cp_dir = root / ".sac" / "checkpoints" / checkpoint_id
    cp_dir.mkdir(parents=True, exist_ok=True)
    metadata = CheckpointMetadata(
        checkpoint_id=checkpoint_id,
        task=state.goal,
        patch_id="p",
        created_at="2026-01-01T00:00:00Z",
        file_operations=[CheckpointFileOperation(path=f, operation="update", existed_before=True) for f in files],
    )
    (cp_dir / "metadata.json").write_text(json.dumps(metadata.model_dump()), encoding="utf-8")
    updated = state.model_copy(update={"status": "applied", "audit_trace_ids": [checkpoint_id]})
    TaskStore(root).save(updated)
    return updated


def _write_pending(root: Path) -> None:
    pending = PatchProposal(
        id="pending-1",
        task="Inspect task diff",
        created_at="2026-01-01T00:00:00Z",
        model="test",
        blocks=[
            PatchBlock(
                operation="update",
                file_path=Path("config.py"),
                search='api_key = "old"\n',
                replace='api_key = "ghp_abcdefghijklmnop1234567890abcdef"\n',
            )
        ],
    )
    path = root / ".sac" / "pending_patch.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pending.model_dump_json(indent=2), encoding="utf-8")


class TestSacDiffTask:
    def test_missing_task_returns_deterministic_empty_json(self, tmp_path):
        root = _repo(tmp_path)
        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["diff", "--task", "no-such-task", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"] == {"diff": "", "files": [], "task_id": "no-such-task"}

    def test_applied_files_display_and_json_shape(self, tmp_path):
        root = _repo(tmp_path)
        state = _task_with_checkpoint(root, ["app.py"])
        (root / "app.py").write_text("print('changed')\n", encoding="utf-8")

        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["diff", "--task", state.task_id, "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["command"] == "diff --task"
        assert data["status"] == "success"
        assert data["data"]["files"] == ["app.py"]
        assert "print('changed')" in data["data"]["diff"]

    def test_pending_patch_display_is_redacted(self, tmp_path):
        root = _repo(tmp_path)
        _task_with_checkpoint(root, ["app.py"])
        _write_pending(root)

        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["diff", "--task", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["data"]["files"] == ["app.py", "config.py"]
        assert "ghp_abcdefghijklmnop1234567890abcdef" not in data["data"]["diff"]
        assert "[REDACTED]" in data["data"]["diff"]

    def test_read_only_no_staging_or_file_writes(self, tmp_path):
        root = _repo(tmp_path)
        _task_with_checkpoint(root, ["app.py"])
        (root / "app.py").write_text("print('changed')\n", encoding="utf-8")
        before_status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")

        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["diff", "--task", "--json"])

        after_status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
        assert result.exit_code == 0
        assert _git(root, "diff", "--cached", "--name-only") == ""
        assert before_status == after_status

    def test_files_are_deterministically_ordered(self, tmp_path):
        root = _repo(tmp_path)
        state = _task_with_checkpoint(root, ["config.py", "app.py"])
        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["diff", "--task", state.task_id, "--json"])
        assert json.loads(result.output)["data"]["files"] == ["app.py", "config.py"]
