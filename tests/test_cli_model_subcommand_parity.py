"""Tests for v4.14.2 --model parity on subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()

_SUBCOMMANDS_WITH_MODEL = ["ask", "edit", "fix", "run", "shell", "agent"]


class TestModelHelpDocs:
    @pytest.mark.parametrize("cmd", ["ask", "edit", "fix", "run", "shell"])
    def test_subcommand_help_documents_model(self, cmd: str) -> None:
        result = runner.invoke(app, [cmd, "--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "--model" in result.stdout

    def test_agent_run_help_documents_model(self) -> None:
        result = runner.invoke(app, ["agent", "run", "--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "--model" in result.stdout

    def test_root_help_documents_model(self) -> None:
        result = runner.invoke(app, ["--help"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "--model" in result.stdout


class TestModelFlagAccepted:
    def test_ask_accepts_model_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        # Use same provider to avoid provider switching issues in test
        result = runner.invoke(
            app, ["ask", "--model", "mock:gpt-4.1-mini", "what is this?"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_edit_accepts_model_flag_and_prints_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        # Verify --model is parsed (override message in output). The mock
        # patch may fail on an empty tree, so we check for the override text.
        result = runner.invoke(
            app, ["edit", "--model", "mock:gpt-4.1-mini", "add a docstring"],
            catch_exceptions=False,
        )
        assert "Session model override: gpt-4.1-mini" in result.stdout

    def test_fix_accepts_model_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["fix", "--model", "mock:gpt-4.1-mini", "--test-command", "echo ok"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_run_accepts_model_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["run", "--model", "mock:gpt-4.1-mini", "echo hello"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0


class TestModelEnvOverrideOrder:
    def test_subcommand_model_sets_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        import os
        monkeypatch.delenv("SAFECODE_LLM_MODEL", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_PROVIDER", raising=False)
        result = runner.invoke(
            app, ["ask", "--model", "mock:gpt-4.1-mini", "test"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert os.getenv("SAFECODE_LLM_MODEL") is not None
        assert os.getenv("SAFECODE_LLM_PROVIDER") is not None
