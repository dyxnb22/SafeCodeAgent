"""Tests for v4.15.0 sac init guided first-run wizard."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_init import run_init

runner = CliRunner()


class TestInitHelpAndNonTTY:
    def test_init_visible_in_root_help(self) -> None:
        result = runner.invoke(app, ["--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "init" in result.stdout

    def test_init_help_shows_options(self) -> None:
        result = runner.invoke(app, ["init", "--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "--provider" in result.stdout
        assert "--api-key" in result.stdout
        assert "--policy" in result.stdout

    def test_non_tty_prints_static_template(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force non-TTY by running through run_init directly
        code = run_init(tmp_path, is_tty=False)
        assert code == 0


class TestInitFlags:
    def test_init_with_provider_and_policy_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        # Non-TTY + flags should produce a static template with exit 0
        result = runner.invoke(
            app,
            ["init", "--provider", "deepseek", "--policy", "balanced", "--yes"],
            catch_exceptions=False,
        )
        # Non-TTY prints template and exits 0
        assert result.exit_code == 0

    def test_setup_is_hidden_from_help(self) -> None:
        result = runner.invoke(app, ["--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "setup" not in result.stdout

    def test_setup_still_callable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["setup", "--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "--wizard" in result.stdout


class TestInitPolicyRefusal:
    def test_init_refuses_unknown_provider(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        # Non-TTY with invalid provider
        result = runner.invoke(
            app,
            ["init", "--provider", "nonexistent", "--yes"],
            catch_exceptions=False,
        )
        assert result.exit_code == 1

    def test_init_refuses_unknown_policy(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["init", "--provider", "deepseek", "--policy", "nonexistent", "--yes"],
            catch_exceptions=False,
        )
        assert result.exit_code == 1
