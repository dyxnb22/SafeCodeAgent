"""Tests for v4.5.0 dirty worktree guard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.cli import app
from safecode.git.local import dirty_tree_guard
from safecode.task.store import TaskStore

runner = CliRunner()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "sac@example.test")
    _git(tmp_path, "config", "user.name", "SafeCode Test")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md", "src/app.py")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _task(root: Path, files: list[str]):
    state = TaskStore(root).create("Change app")
    checkpoint_id = "2026-01-01T00-00-00_cp"
    cp_dir = root / ".sac" / "checkpoints" / checkpoint_id
    cp_dir.mkdir(parents=True, exist_ok=True)
    metadata = CheckpointMetadata(
        checkpoint_id=checkpoint_id,
        task="Change app",
        patch_id="p",
        created_at="2026-01-01T00:00:00Z",
        file_operations=[CheckpointFileOperation(path=f, operation="update", existed_before=True) for f in files],
    )
    (cp_dir / "metadata.json").write_text(json.dumps(metadata.model_dump()), encoding="utf-8")
    TaskStore(root).save(state.model_copy(update={"status": "applied", "audit_trace_ids": [checkpoint_id]}))


class TestDirtyWorktreeGuard:
    def test_unrelated_tracked_change_refuses_commit(self, tmp_path):
        root = _repo(tmp_path)
        _task(root, ["src/app.py"])
        (root / "src" / "app.py").write_text("print('task')\n", encoding="utf-8")
        (root / "README.md").write_text("dirty\n", encoding="utf-8")

        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["commit", "--json"])

        assert result.exit_code == 1
        assert "README.md" in json.loads(result.output)["error"]

    def test_untracked_outside_touched_dirs_ignored(self, tmp_path):
        root = _repo(tmp_path)
        (root / "notes.txt").write_text("ignored\n", encoding="utf-8")
        guard = dirty_tree_guard(root, {"src/app.py"})
        assert guard.ok

    def test_untracked_inside_touched_dirs_blocked(self, tmp_path):
        root = _repo(tmp_path)
        (root / "src" / "scratch.py").write_text("block\n", encoding="utf-8")
        guard = dirty_tree_guard(root, {"src/app.py"})
        assert not guard.ok
        assert guard.unrelated_files == ("src/scratch.py",)

    def test_no_push_or_remote_operations_in_git_helper(self):
        source = Path("src/safecode/git/local.py").read_text(encoding="utf-8")
        assert '"push"' not in source
        assert '"remote"' not in source
