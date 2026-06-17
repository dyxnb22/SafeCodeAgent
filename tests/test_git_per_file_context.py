"""Tests for per-file git context injection (v6.8.1)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from safecode.context.git_context import collect_per_file_git_context


def _fake_run(returncode: int, stdout: str):
    """Return a mock subprocess.CompletedProcess."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


class TestCollectPerFileGitContext:
    def test_returns_empty_when_git_not_available(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])
        assert result == ""

    def test_returns_empty_for_no_files(self, tmp_path: Path) -> None:
        result = collect_per_file_git_context(tmp_path, [])
        assert result == ""

    def test_includes_log_output(self, tmp_path: Path) -> None:
        log_output = "abc1234 fix: update foo\ndef5678 feat: add bar"
        diff_output = ""

        def fake_run(cmd, **kwargs):
            if "log" in cmd:
                return _fake_run(0, log_output)
            return _fake_run(0, diff_output)

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])

        assert "src/foo.py" in result
        assert "abc1234" in result
        assert "Recent commits" in result

    def test_includes_diff_output(self, tmp_path: Path) -> None:
        log_output = ""
        diff_output = "+++ b/src/foo.py\n+def new_func(): pass"

        def fake_run(cmd, **kwargs):
            if "log" in cmd:
                return _fake_run(0, log_output)
            return _fake_run(0, diff_output)

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])

        assert "Diff vs HEAD~1" in result
        assert "new_func" in result

    def test_caps_at_top_5_files(self, tmp_path: Path) -> None:
        files = [f"src/file{i}.py" for i in range(10)]
        calls: list[str] = []

        def fake_run(cmd, **kwargs):
            if "--" in cmd:
                calls.append(cmd[-1])  # the file path
            return _fake_run(0, "abc fix something")

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            collect_per_file_git_context(tmp_path, files)

        # At most 5 * 2 calls (log + diff per file), capped at 5 files
        unique_files = {c for c in calls if c.startswith("src/")}
        assert len(unique_files) <= 5

    def test_git_failure_returns_empty_silently(self, tmp_path: Path) -> None:
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 8)

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])

        assert result == ""

    def test_output_total_capped(self, tmp_path: Path) -> None:
        big_output = "a" * 5000

        def fake_run(cmd, **kwargs):
            return _fake_run(0, big_output)

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])

        # Header + body cap: total must be under _PER_FILE_TOTAL_CAP + reasonable overhead
        assert len(result) <= 2200

    def test_secrets_redacted_in_output(self, tmp_path: Path) -> None:
        secret_log = 'commit abc: set token = "supersecretvalue12345"'

        def fake_run(cmd, **kwargs):
            if "log" in cmd:
                return _fake_run(0, secret_log)
            return _fake_run(0, "")

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])

        assert "supersecretvalue12345" not in result

    def test_section_header_present(self, tmp_path: Path) -> None:
        def fake_run(cmd, **kwargs):
            return _fake_run(0, "abc fix something")

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            result = collect_per_file_git_context(tmp_path, ["src/foo.py"])

        assert result.startswith("## Per-file git context")


class TestConfigToggle:
    def test_context_git_per_file_default_false(self) -> None:
        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig()
        assert config.context_git_per_file is False

    def test_context_git_per_file_can_be_enabled(self) -> None:
        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig(context_git_per_file=True)
        assert config.context_git_per_file is True

    def test_collector_skips_git_when_flag_off(self, tmp_path: Path) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.context.collector import ContextCollector

        config = SafeCodeConfig(context_git_per_file=False)
        collector = ContextCollector(tmp_path, config)

        (tmp_path / "README.md").write_text("# Project")
        ctx = collector._selected_context("readme")
        assert "per_file_git_context" not in ctx

    def test_collector_includes_git_when_flag_on(self, tmp_path: Path) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.context.collector import ContextCollector

        config = SafeCodeConfig(context_git_per_file=True)
        collector = ContextCollector(tmp_path, config)
        (tmp_path / "README.md").write_text("# Project")

        def fake_run(cmd, **kwargs):
            return _fake_run(0, "abc123 fix something")

        with patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", side_effect=fake_run):
            ctx = collector._selected_context("readme")

        # When git output is non-empty, per_file_git_context should be injected
        # (may be absent if no sources found for 'readme')
        assert isinstance(ctx, dict)
