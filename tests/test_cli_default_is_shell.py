"""Tests for v4.16.0 bare sac enters shell and 7-command help surface."""

from __future__ import annotations

from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


class TestBareSacShell:
    def test_sac_no_args_help_shows_daily_commands(self) -> None:
        result = runner.invoke(app, ["--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "ask" in result.stdout
        assert "edit" in result.stdout
        assert "apply" in result.stdout
        assert "fix" in result.stdout
        assert "commit" in result.stdout
        assert "doctor" in result.stdout

    def test_sac_help_all_shows_full_surface(self) -> None:
        result = runner.invoke(app, ["help", "--all"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Daily Commands" in result.stdout
        assert "Advanced & Experimental" in result.stdout
        assert "quickstart" in result.stdout
        assert "shell" in result.stdout
        assert "model" in result.stdout

    def test_sac_help_without_all_shows_hint(self) -> None:
        result = runner.invoke(app, ["help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "sac help --all" in result.stdout

    def test_hidden_commands_still_callable(self) -> None:
        for cmd in ["quickstart", "status", "shell", "model", "provider",
                     "version", "task", "memory", "debug", "rollback", "run",
                     "profile", "resume"]:
            result = runner.invoke(app, [cmd, "--help"], catch_exceptions=False)
            assert result.exit_code == 0, f"{cmd} --help should exit 0"
