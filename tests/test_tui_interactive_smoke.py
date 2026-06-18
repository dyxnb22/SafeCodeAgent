"""Smoke tests for v3.5.2 tui-interactive.

Verifies:
- sac tui interactive command is registered.
- Non-TTY mode exits 0 and produces SafeCode dashboard content.
- run_interactive in non-TTY mode writes static snapshot to stdout.
- Output contains expected session/plan/diff/history sections.
- Non-TTY output is deterministic (same output on repeated calls).
- sac tui dashboard (existing command) still works.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.agent.session import AgentSessionStore
from safecode.cli import app
from safecode.state.journal import AgentJournalStore
from safecode.tui.interactive import run_interactive

runner = CliRunner()


# ── Unit: run_interactive ─────────────────────────────────────────────────────


class TestRunInteractiveNonTTY:
    def test_returns_without_error_empty_project(self, tmp_path):
        """Non-TTY mode should complete immediately without raising."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        assert buf.getvalue() != ""

    def test_output_contains_safecode_tui(self, tmp_path):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        assert "SafeCode TUI" in buf.getvalue()

    def test_output_contains_session_section(self, tmp_path):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        assert "Session" in buf.getvalue()

    def test_output_contains_pending_diff_section(self, tmp_path):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        assert "Pending Diff" in buf.getvalue()

    def test_output_contains_history_section(self, tmp_path):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        assert "History" in buf.getvalue()

    def test_deterministic_output_empty_project(self, tmp_path):
        buf1 = io.StringIO()
        buf2 = io.StringIO()
        with patch("sys.stdout", buf1):
            run_interactive(tmp_path)
        with patch("sys.stdout", buf2):
            run_interactive(tmp_path)
        assert buf1.getvalue() == buf2.getvalue()

    def test_shows_session_goal_when_present(self, tmp_path):
        state = AgentSessionStore(tmp_path).start("Test the feature", plan=["Step 1"])
        AgentJournalStore(tmp_path).record_plan(state.session_id, state.goal, state.plan)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        output = buf.getvalue()
        assert "Test the feature" in output

    def test_shows_plan_items_when_present(self, tmp_path):
        state = AgentSessionStore(tmp_path).start("goal", plan=["Inspect files", "Write patch"])
        AgentJournalStore(tmp_path).record_plan(state.session_id, state.goal, state.plan)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        output = buf.getvalue()
        assert "Inspect files" in output

    def test_history_limit_respected(self, tmp_path):
        """history_limit=1 should produce output without error."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path, history_limit=1)
        assert "SafeCode TUI" in buf.getvalue()


class TestRunInteractiveTTYBranch:
    def test_tty_mode_calls_run_live(self, tmp_path):
        """When stdout is a TTY, _run_live should be called."""
        with patch("safecode.tui.interactive._run_live") as mock_live, \
             patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            run_interactive(tmp_path)
        mock_live.assert_called_once()

    def test_non_tty_mode_calls_print_static(self, tmp_path):
        """When stdout is not a TTY, _print_static should be called."""
        with patch("safecode.tui.interactive._print_static") as mock_static, \
             patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            run_interactive(tmp_path)
        mock_static.assert_called_once()


# ── CLI: sac tui interactive ──────────────────────────────────────────────────


class TestCLITuiInteractive:
    def test_interactive_command_registered(self):
        result = runner.invoke(app, ["tui", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.output.lower()

    def test_interactive_help_mentions_experimental(self):
        result = runner.invoke(app, ["tui", "interactive", "--help"])
        assert result.exit_code == 0
        assert "experimental" in result.output.lower()

    def test_interactive_non_tty_exits_zero(self, tmp_path, monkeypatch):
        """CliRunner uses non-TTY input/output, so interactive should exit 0."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tui", "interactive"])
        assert result.exit_code == 0

    def test_interactive_non_tty_output_has_safecode_tui(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tui", "interactive"])
        assert "SafeCode TUI" in result.output

    def test_interactive_refresh_option_accepted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tui", "interactive", "--refresh", "0.5"])
        assert result.exit_code == 0

    def test_interactive_history_limit_option_accepted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tui", "interactive", "--history-limit", "3"])
        assert result.exit_code == 0


# ── Regression: sac tui dashboard still works ─────────────────────────────────


class TestExistingTuiDashboardUnchanged:
    def test_dashboard_cli_still_exits_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tui", "dashboard"])
        assert result.exit_code == 0
        assert "SafeCode TUI" in result.output


# ── v3.9.2 T-3.9.2-B: TUI frozen experimental ────────────────────────────────


class TestTUIFrozenExperimental:
    """v3.9.2 decision: freeze sac tui interactive at v3.5.2 behavior (Option B).

    The TUI is labeled EXPERIMENTAL in help text. No Textual dependency
    introduced. Output remains Rich-based and deterministic.
    """

    def test_interactive_still_exits_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tui", "interactive"])
        assert result.exit_code == 0

    def test_interactive_still_experimental_label(self):
        result = runner.invoke(app, ["tui", "interactive", "--help"])
        assert result.exit_code == 0
        assert "experimental" in result.output.lower()

    def test_no_textual_import(self):
        """Textual must not be imported in the TUI module."""
        import ast
        tui_path = (
            Path(__file__).parent.parent / "src" / "safecode" / "tui" / "interactive.py"
        )
        tree = ast.parse(tui_path.read_text(encoding="utf-8"))
        imports = [
            node.names[0].name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        ]
        from_imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        all_imports = imports + from_imports
        assert not any("textual" in m.lower() for m in all_imports), (
            "Textual must not be imported in interactive.py (decision: freeze experimental)"
        )

    def test_non_tty_output_still_has_safecode_tui(self, tmp_path):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            run_interactive(tmp_path)
        assert "SafeCode TUI" in buf.getvalue()
