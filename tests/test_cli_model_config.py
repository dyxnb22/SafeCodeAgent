"""Tests for user-level model configuration UX."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


def test_model_command_persists_user_config(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user.toml"
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "model",
            "gpt-4.1-mini",
            "--provider",
            "openai",
            "--api-key",
            "sk-test-key",
            "--network",
        ],
    )

    assert result.exit_code == 0
    content = user_config.read_text(encoding="utf-8")
    assert 'provider = "openai"' in content
    assert 'model = "gpt-4.1-mini"' in content
    assert 'api_key = "sk-test-key"' in content
    assert "network_enabled = true" in content


def test_model_command_show_redacts_key(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user.toml"
    user_config.write_text(
        '[llm]\nprovider = "openai"\nmodel = "gpt-4.1-mini"\napi_key = "sk-secret-value"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["model"])

    assert result.exit_code == 0
    assert "API key: configured" in result.output
    assert "sk-secret-value" not in result.output


def test_openai_client_uses_configured_api_key_when_env_missing(tmp_path: Path) -> None:
    from safecode.config import SafeCodeConfig
    from safecode.llm.openai_client import OpenAICompatibleLLMClient

    cfg = SafeCodeConfig()
    cfg.sandbox.network_enabled = True
    cfg.llm.api_key = "sk-configured"

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
    ):
        client = OpenAICompatibleLLMClient(cfg)

    assert client.api_key == "sk-configured"


def test_shell_model_slash_command_persists_user_config(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user.toml"
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["shell", "--non-tty"],
        input="/model claude-sonnet-4-6 --provider anthropic --api-key sk-anthropic\n/exit\n",
    )

    assert result.exit_code == 0
    content = user_config.read_text(encoding="utf-8")
    assert 'provider = "anthropic"' in content
    assert 'model = "claude-sonnet-4-6"' in content
    assert 'api_key = "sk-anthropic"' in content


def test_bare_sac_enters_shell_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, [], input="/exit\n")

    assert result.exit_code == 0
    assert "Exiting shell." in result.output

