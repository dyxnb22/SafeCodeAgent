"""Tests for experimental sac branch new (v4.5.1)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli import app

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


class TestSacBranchNew:
    def test_valid_branch_creation_switches_branch(self, tmp_path):
        root = _repo(tmp_path)
        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["branch", "new", "feature/safe-local", "--json"])
        assert result.exit_code == 0, result.output
        assert _git(root, "branch", "--show-current") == "feature/safe-local"

    def test_invalid_names_refuse(self, tmp_path):
        root = _repo(tmp_path)
        bad_names = ["", "   ", "-bad", "bad name", "bad;name", "bad..name", "bad~name", "bad\\name"]
        for name in bad_names:
            with patch("safecode.cli_commit.Path") as mock_path:
                mock_path.cwd.return_value = root
                result = runner.invoke(app, ["branch", "new", name, "--json"])
            assert result.exit_code != 0

    def test_existing_branch_refuses(self, tmp_path):
        root = _repo(tmp_path)
        _git(root, "branch", "already-there")
        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["branch", "new", "already-there", "--json"])
        assert result.exit_code == 1
        assert "already exists" in json.loads(result.output)["error"]

    def test_dirty_unrelated_refuses(self, tmp_path):
        root = _repo(tmp_path)
        (root / "README.md").write_text("dirty\n", encoding="utf-8")
        with patch("safecode.cli_commit.Path") as mock_path:
            mock_path.cwd.return_value = root
            result = runner.invoke(app, ["branch", "new", "new-branch", "--json"])
        assert result.exit_code == 1
        assert "README.md" in json.loads(result.output)["error"]

    def test_branch_helper_never_uses_force_or_reset(self):
        source = Path("src/safecode/git/local.py").read_text(encoding="utf-8")
        assert '"reset"' not in source
        assert "-B" not in source

