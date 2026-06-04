"""Tests for rollback-after-commit warning (v4.5.1)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.cli import app
from safecode.task.store import TaskStore

runner = CliRunner()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "sac@example.test")
    _git(tmp_path, "config", "user.name", "SafeCode Test")
    (tmp_path / "app.py").write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _checkpoint(root: Path) -> CheckpointMetadata:
    state = TaskStore(root).create("Change app")
    checkpoint_id = "2026-01-01T00-00-00_cp"
    cp_dir = root / ".sac" / "checkpoints" / checkpoint_id
    backup = cp_dir / "files" / "app.py"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text("before\n", encoding="utf-8")
    metadata = CheckpointMetadata(
        checkpoint_id=checkpoint_id,
        task="Change app",
        patch_id="p",
        created_at="2026-01-01T00:00:00Z",
        file_operations=[
            CheckpointFileOperation(path="app.py", operation="update", existed_before=True, backup_path="files/app.py")
        ],
    )
    (cp_dir / "metadata.json").write_text(json.dumps(metadata.model_dump()), encoding="utf-8")
    TaskStore(root).save(state.model_copy(update={"status": "applied", "audit_trace_ids": [checkpoint_id]}))
    return metadata


class TestRollbackAfterCommit:
    def test_rollback_refuses_after_commit_with_revert_hint(self, tmp_path):
        root = _repo(tmp_path)
        _checkpoint(root)
        (root / "app.py").write_text("after\n", encoding="utf-8")
        _git(root, "add", "app.py")
        _git(root, "commit", "-m", "apply task")

        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["rollback", "--last"])

        assert result.exit_code == 1
        assert "git revert" in result.output
        assert (root / "app.py").read_text(encoding="utf-8") == "after\n"

    def test_force_uncommit_allows_rollback_and_audits_sha(self, tmp_path):
        root = _repo(tmp_path)
        _checkpoint(root)
        (root / "app.py").write_text("after\n", encoding="utf-8")
        _git(root, "add", "app.py")
        _git(root, "commit", "-m", "apply task")

        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["rollback", "--last", "--force-uncommit"])

        assert result.exit_code == 0, result.output
        assert (root / "app.py").read_text(encoding="utf-8") == "before\n"
        events = (root / ".sac" / "logs" / "events.jsonl").read_text(encoding="utf-8")
        assert "rollback_force_uncommit" in events
        assert "commit_sha" in events

    def test_uncommitted_apply_rollback_behavior_unchanged(self, tmp_path):
        root = _repo(tmp_path)
        _checkpoint(root)
        (root / "app.py").write_text("after\n", encoding="utf-8")

        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["rollback", "--last"])

        assert result.exit_code == 0, result.output
        assert (root / "app.py").read_text(encoding="utf-8") == "before\n"
