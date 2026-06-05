"""Tests for v4.15.1 session-scoped model switching."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


class TestModelSessionOnly:
    def test_model_switch_is_session_only_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SAFECODE_LLM_MODEL", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_PROVIDER", raising=False)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["model", "mock:gpt-4.1-mini"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Session model override" in result.stdout
        assert "Session-only" in result.stdout

    def test_model_status_shows_session_and_persisted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        user_config.write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)
        # Set a session override
        monkeypatch.setenv("SAFECODE_LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("SAFECODE_LLM_MODEL", "deepseek-v4-flash")

        result = runner.invoke(app, ["model", "status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Session override" in result.stdout
        assert "deepseek-v4-flash" in result.stdout

    def test_model_status_no_session_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        user_config.write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SAFECODE_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_MODEL", raising=False)

        result = runner.invoke(app, ["model", "status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No session override active" in result.stdout

    def test_model_without_args_shows_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        user_config.write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["model"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Model Status" in result.stdout
        assert "Persisted provider" in result.stdout


class TestModelSaveFlag:
    def test_save_flag_persists_to_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        # Pre-create with a deepseek profile so switching works
        user_config.write_text(
            '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\n'
            'base_url = "https://api.deepseek.com/v1"\n'
            '[providers]\nactive = "deepseek"\n'
            '[providers.deepseek]\nbase_url = "https://api.deepseek.com/v1"\n'
            'default_model = "deepseek-v4-flash"\n'
            'model_aliases = {flash = "deepseek-v4-flash", pro = "deepseek-v4-pro"}\n'
            'network_allowlist = ["api.deepseek.com"]\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["model", "--save", "pro"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "saved globally" in result.stdout


class TestLegacyFlag:
    def test_legacy_persist_env_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SAFECODE_LEGACY_MODEL_PERSIST", "1")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["model", "mock:gpt-4.1-mini"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "deprecated" in result.stdout.lower()
