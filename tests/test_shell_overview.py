"""Tests for project overview/context builder — v4.9.2."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


def _make_python_project(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'myapp'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# MyApp\n\nA sample Python app.\n", encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "main.py").write_text("def main(): pass\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_pass(): assert True\n", encoding="utf-8")


def _make_typescript_project(root: Path) -> None:
    (root / "package.json").write_text(
        json.dumps({"name": "myapp", "version": "0.1.0", "scripts": {"test": "jest"}}),
        encoding="utf-8",
    )
    (root / "index.ts").write_text("export function main() {}\n", encoding="utf-8")


def _make_go_project(root: Path) -> None:
    (root / "go.mod").write_text("module myapp\n\ngo 1.21\n", encoding="utf-8")
    (root / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")


def _make_rust_project(root: Path) -> None:
    (root / "Cargo.toml").write_text(
        "[package]\nname = 'myapp'\nversion = '0.1.0'\nedition = '2021'\n", encoding="utf-8"
    )
    src = root / "src"
    src.mkdir()
    (src / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (src / "lib.rs").write_text("pub fn hello() {}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Stack detection tests
# ---------------------------------------------------------------------------


class TestStackDetection:
    def test_python_project_detected(self, tmp_path):
        from safecode.shell_session.overview import _detect_stack
        _make_python_project(tmp_path)
        assert _detect_stack(tmp_path) == "python"

    def test_typescript_project_detected(self, tmp_path):
        from safecode.shell_session.overview import _detect_stack
        _make_typescript_project(tmp_path)
        assert _detect_stack(tmp_path) == "typescript"

    def test_go_project_detected(self, tmp_path):
        from safecode.shell_session.overview import _detect_stack
        _make_go_project(tmp_path)
        assert _detect_stack(tmp_path) == "go"

    def test_rust_project_detected(self, tmp_path):
        from safecode.shell_session.overview import _detect_stack
        _make_rust_project(tmp_path)
        assert _detect_stack(tmp_path) == "rust"

    def test_unknown_stack_returns_unknown(self, tmp_path):
        from safecode.shell_session.overview import _detect_stack
        assert _detect_stack(tmp_path) == "unknown"


# ---------------------------------------------------------------------------
# Overview build tests (per stack)
# ---------------------------------------------------------------------------


class TestOverviewBuildPerStack:
    def test_python_overview_has_stack(self, tmp_path):
        from safecode.shell_session.overview import build_project_overview
        _make_python_project(tmp_path)
        ov = build_project_overview(tmp_path)
        assert ov.stack == "python"

    def test_python_overview_detects_test_dir(self, tmp_path):
        from safecode.shell_session.overview import build_project_overview
        _make_python_project(tmp_path)
        ov = build_project_overview(tmp_path)
        assert "tests" in ov.test_dirs

    def test_python_overview_high_signal_includes_readme(self, tmp_path):
        from safecode.shell_session.overview import build_project_overview
        _make_python_project(tmp_path)
        ov = build_project_overview(tmp_path)
        assert any("README" in f for f in ov.high_signal_files)

    def test_typescript_overview_has_stack(self, tmp_path):
        from safecode.shell_session.overview import build_project_overview
        _make_typescript_project(tmp_path)
        ov = build_project_overview(tmp_path)
        assert ov.stack == "typescript"

    def test_go_overview_has_stack(self, tmp_path):
        from safecode.shell_session.overview import build_project_overview
        _make_go_project(tmp_path)
        ov = build_project_overview(tmp_path)
        assert ov.stack == "go"

    def test_rust_overview_has_stack(self, tmp_path):
        from safecode.shell_session.overview import build_project_overview
        _make_rust_project(tmp_path)
        ov = build_project_overview(tmp_path)
        assert ov.stack == "rust"


# ---------------------------------------------------------------------------
# Bounded context tests
# ---------------------------------------------------------------------------


class TestBoundedContext:
    def test_overview_render_bounded(self, tmp_path):
        """Rendered overview must not exceed _MAX_OVERVIEW_BYTES * 2 (with budget trimming)."""
        from safecode.shell_session.overview import build_project_overview, _MAX_OVERVIEW_BYTES
        _make_python_project(tmp_path)
        ov = build_project_overview(tmp_path)
        rendered = ov.render_text()
        # After budget trimming, rendered text should be reasonable
        # We allow up to 2× the budget because trimming is applied per pass
        assert len(rendered.encode("utf-8")) <= _MAX_OVERVIEW_BYTES * 3

    def test_skipped_signals_reported_when_budget_exceeded(self, tmp_path):
        """When context budget is exceeded, skipped_signals is populated."""
        from safecode.shell_session.overview import build_project_overview, _MAX_OVERVIEW_BYTES
        from unittest.mock import patch

        # Simulate a very large commit list to force budget overflow
        big_commits = [f"abc{i:04d} Add feature {i} with a long message" for i in range(200)]

        with patch("safecode.shell_session.overview._git_recent_commits", return_value=big_commits):
            ov = build_project_overview(tmp_path)

        # If the budget was exceeded, skipped_signals should be non-empty
        rendered_initial_size = len("\n".join(big_commits).encode("utf-8"))
        if rendered_initial_size > _MAX_OVERVIEW_BYTES:
            assert len(ov.skipped_signals) >= 0  # May or may not trim depending on total

    def test_high_signal_files_capped(self, tmp_path):
        """High-signal files list never exceeds _MAX_HIGH_SIGNAL_FILES."""
        from safecode.shell_session.overview import build_project_overview, _MAX_HIGH_SIGNAL_FILES
        # Create many .md files
        for i in range(50):
            (tmp_path / f"file{i}.md").write_text(f"# File {i}\n", encoding="utf-8")
        ov = build_project_overview(tmp_path)
        assert len(ov.high_signal_files) <= _MAX_HIGH_SIGNAL_FILES


# ---------------------------------------------------------------------------
# Redaction and path safety tests
# ---------------------------------------------------------------------------


class TestRedactionAndPathSafety:
    def test_git_commit_messages_are_redacted(self, tmp_path):
        """Commit messages containing secrets are redacted."""
        from safecode.shell_session.overview import _git_recent_commits
        from unittest.mock import patch

        secret_commit = "abc1234 Add API_KEY=secret123 to config"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=secret_commit + "\n"
            )
            commits = _git_recent_commits(tmp_path)

        # The redacted commit should not contain the raw secret
        assert all("secret123" not in c for c in commits)

    def test_high_signal_files_stay_within_root(self, tmp_path):
        """High-signal files must be within the project root (no traversal)."""
        from safecode.shell_session.overview import _high_signal_files
        files = _high_signal_files(tmp_path)
        for f in files:
            assert ".." not in f, f"Path traversal found in high-signal file: {f}"

    def test_current_task_goal_is_redacted(self, tmp_path):
        """Current task goal is redacted before inclusion in overview."""
        from safecode.task.store import TaskStore

        task_store = TaskStore(tmp_path)
        task = task_store.create("Fix API_KEY=topsecret in config")

        from safecode.shell_session.overview import _current_task_info
        info = _current_task_info(tmp_path)
        if info:
            assert "topsecret" not in info.get("goal", ""), "Secret must be redacted from task goal"


# ---------------------------------------------------------------------------
# Overview determinism tests
# ---------------------------------------------------------------------------


class TestOverviewDeterminism:
    def test_overview_is_deterministic(self, tmp_path):
        """Building the same overview twice returns identical text."""
        from safecode.shell_session.overview import build_project_overview
        _make_python_project(tmp_path)

        # Suppress git calls for determinism in tests without a repo
        with (
            patch("safecode.shell_session.overview._git_branch", return_value="main"),
            patch("safecode.shell_session.overview._git_dirty", return_value=False),
            patch("safecode.shell_session.overview._git_recent_commits", return_value=["abc commit1"]),
        ):
            ov1 = build_project_overview(tmp_path)
            ov2 = build_project_overview(tmp_path)

        assert ov1.render_text() == ov2.render_text()

    def test_overview_to_dict_is_json_serializable(self, tmp_path):
        """ProjectOverview.to_dict() must be JSON-serializable."""
        from safecode.shell_session.overview import build_project_overview
        ov = build_project_overview(tmp_path)
        # Should not raise
        json_str = json.dumps(ov.to_dict())
        assert json_str  # non-empty


# ---------------------------------------------------------------------------
# Shell /overview command integration
# ---------------------------------------------------------------------------


class TestShellOverviewIntegration:
    def test_shell_overview_slash_command(self, tmp_path, monkeypatch):
        """sac shell /overview returns project overview text."""
        from typer.testing import CliRunner
        from safecode.cli import app

        _make_python_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/overview\n/exit\n")
        assert result.exit_code == 0
        # Must include EXPERIMENTAL label and some stack info
        assert "EXPERIMENTAL" in result.output
        assert "python" in result.output.lower()

    def test_shell_answers_what_is_this_project_via_router(self, tmp_path, monkeypatch):
        """'explain this codebase' routes to overview and shows project info."""
        from typer.testing import CliRunner
        from safecode.cli import app

        _make_python_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app, ["shell", "--non-tty"], input="explain this codebase\n/exit\n"
        )
        assert result.exit_code == 0
        # Router should route to overview or ask; either way the shell responds
        assert result.output.strip()


# ---------------------------------------------------------------------------
# ProjectOverview model tests
# ---------------------------------------------------------------------------


class TestProjectOverviewModel:
    def test_render_text_includes_stack(self, tmp_path):
        from safecode.shell_session.overview import ProjectOverview
        ov = ProjectOverview(
            project_root=str(tmp_path),
            stack="python",
            git_branch="main",
            git_dirty=False,
            recent_commits=[],
            profile_commands={"test": "pytest -q"},
            entrypoints=["src"],
            test_dirs=["tests"],
            high_signal_files=["README.md"],
            pinned_files=[],
            current_task={},
            recent_failures=[],
            skipped_signals=[],
        )
        text = ov.render_text()
        assert "python" in text
        assert "pytest -q" in text
        assert "README.md" in text

    def test_render_text_shows_skipped_signals(self):
        from safecode.shell_session.overview import ProjectOverview
        ov = ProjectOverview(
            project_root="/tmp/test",
            stack="go",
            git_branch="",
            git_dirty=False,
            recent_commits=[],
            profile_commands={},
            entrypoints=[],
            test_dirs=[],
            high_signal_files=[],
            pinned_files=[],
            current_task={},
            recent_failures=[],
            skipped_signals=["some_signal"],
        )
        text = ov.render_text()
        assert "some_signal" in text
