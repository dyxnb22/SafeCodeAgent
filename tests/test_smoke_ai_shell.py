"""Tests for sac smoke ai-shell — v4.9.3."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSmokeAiShellCommand:
    def test_smoke_ai_shell_registered(self):
        """sac smoke ai-shell must be registered and callable."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["smoke", "ai-shell", "--help"])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output

    def test_smoke_ai_shell_all_scenarios_pass(self, tmp_path, monkeypatch):
        """All ai-shell smoke scenarios must pass."""
        monkeypatch.chdir(tmp_path)
        from safecode.cli_smoke import run_ai_shell_smoke

        result = run_ai_shell_smoke()
        failed = [s.name for s in result.scenarios if not s.passed]
        assert not failed, f"AI shell smoke scenarios failed: {failed}"

    def test_smoke_ai_shell_json_output(self, tmp_path, monkeypatch):
        """sac smoke ai-shell --json produces JSON with pass/fail structure."""
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["smoke", "ai-shell", "--json"])
        # May pass or fail; output must be valid JSON structure
        assert '"all_passed"' in result.output or '"command"' in result.output

    def test_smoke_ai_shell_scenario_names(self):
        """Smoke scenarios have expected names."""
        from safecode.cli_smoke import _AI_SHELL_SCENARIOS

        names = {name for name, _ in _AI_SHELL_SCENARIOS}
        assert "session-create-and-persist" in names
        assert "corrupt-session-fail-safe" in names
        assert "intent-router-read-only" in names
        assert "non-tty-no-auto-apply" in names

    def test_smoke_ai_shell_only_filter(self, tmp_path, monkeypatch):
        """--only filter runs only the specified scenario."""
        monkeypatch.chdir(tmp_path)
        from safecode.cli_smoke import run_ai_shell_smoke

        result = run_ai_shell_smoke(only=["session-create-and-persist"])
        assert len(result.scenarios) == 1
        assert result.scenarios[0].name == "session-create-and-persist"


class TestAiShellSmokeScenarios:
    def test_session_create_scenario(self, tmp_path):
        from safecode.cli_smoke import _ai_shell_scenario_session_create_and_persist
        _ai_shell_scenario_session_create_and_persist(tmp_path)

    def test_corrupt_session_scenario(self, tmp_path):
        from safecode.cli_smoke import _ai_shell_scenario_corrupt_session_fail_safe
        _ai_shell_scenario_corrupt_session_fail_safe(tmp_path)

    def test_intent_router_read_only_scenario(self, tmp_path):
        from safecode.cli_smoke import _ai_shell_scenario_intent_router_read_only
        _ai_shell_scenario_intent_router_read_only(tmp_path)

    def test_overview_builds_scenario(self, tmp_path):
        from safecode.cli_smoke import _ai_shell_scenario_overview_builds_for_python_project
        _ai_shell_scenario_overview_builds_for_python_project(tmp_path)

    def test_non_tty_no_auto_apply_scenario(self, tmp_path):
        from safecode.cli_smoke import _ai_shell_scenario_non_tty_no_auto_apply
        _ai_shell_scenario_non_tty_no_auto_apply(tmp_path)

    def test_shell_loop_deterministic_scenario(self, tmp_path):
        from safecode.cli_smoke import _ai_shell_scenario_shell_loop_deterministic
        _ai_shell_scenario_shell_loop_deterministic(tmp_path)
