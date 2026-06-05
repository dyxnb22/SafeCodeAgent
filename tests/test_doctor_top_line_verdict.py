"""Tests for v4.14.1 doctor top-line verdict and next-command hints."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.core.diagnostic import Diagnostic, DiagnosticStatus
from safecode.doctor import Doctor

runner = CliRunner()


def _write_dual_config(tmp_path: Path, monkeypatch, provider: str, model: str, base_url: str,
                       network_enabled: bool = False) -> None:
    """Write both user and project configs for an isolated CLI test."""
    monkeypatch.chdir(tmp_path)
    user_cfg = tmp_path / "user_config.toml"
    user_cfg.write_text(
        f'[llm]\nprovider = "{provider}"\nmodel = "{model}"\n'
        f'base_url = "{base_url}"\n'
        f"[sandbox]\nnetwork_enabled = {str(network_enabled).lower()}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_cfg))
    (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".sac" / "config.toml").write_text(
        f'[llm]\nprovider = "{provider}"\nmodel = "{model}"\n'
        f'base_url = "{base_url}"\n'
        f"[sandbox]\nnetwork_enabled = {str(network_enabled).lower()}\n",
        encoding="utf-8",
    )


class TestDoctorTopLineVerdict:
    def test_verdict_line_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_dual_config(tmp_path, monkeypatch, "mock", "gpt-4.1-mini",
                           "http://localhost:8080/v1")
        result = runner.invoke(app, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Overall:" in result.stdout

    def test_verdict_shows_needs_setup_with_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dual_config(tmp_path, monkeypatch, "deepseek", "deepseek-v4-flash",
                           "https://api.deepseek.com/v1")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_API_KEY", raising=False)
        result = runner.invoke(app, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Overall: NEEDS SETUP" in result.stdout


class TestDoctorNextHints:
    def test_api_key_missing_has_next_in_diagnostics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dual_config(tmp_path, monkeypatch, "deepseek", "deepseek-v4-flash",
                           "https://api.deepseek.com/v1")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_API_KEY", raising=False)
        diagnostics = Doctor(tmp_path).run_diagnostics()
        api_key = [d for d in diagnostics if d.name == "provider_api_key"]
        assert len(api_key) == 1
        assert api_key[0].status == DiagnosticStatus.FAIL
        assert len(api_key[0].hints) >= 1
        assert "sac provider add" in api_key[0].hints[0]

    def test_network_disabled_has_hint_in_diagnostics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dual_config(tmp_path, monkeypatch, "deepseek", "deepseek-v4-flash",
                           "https://api.deepseek.com/v1")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
        diagnostics = Doctor(tmp_path).run_diagnostics()
        net = [d for d in diagnostics if d.name == "provider_network_policy"]
        assert len(net) == 1
        assert net[0].status == DiagnosticStatus.FAIL
        assert len(net[0].hints) >= 1
        assert "sac setup" in net[0].hints[0]


class TestDoctorDiagnosticHintsExist:
    def test_api_key_failure_has_hint_in_diagnostics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dual_config(tmp_path, monkeypatch, "deepseek", "deepseek-v4-flash",
                           "https://api.deepseek.com/v1")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_API_KEY", raising=False)
        diagnostics = Doctor(tmp_path).run_diagnostics()
        api_key = [d for d in diagnostics if d.name == "provider_api_key"]
        assert len(api_key) == 1
        assert api_key[0].status == DiagnosticStatus.FAIL
        assert len(api_key[0].hints) >= 1
        assert "sac provider add" in api_key[0].hints[0]

    def test_experimental_not_in_verdict_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dual_config(tmp_path, monkeypatch, "mock", "gpt-4.1-mini",
                           "http://localhost:8080/v1")
        result = runner.invoke(app, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Overall:" in result.stdout
        verdict_section = result.stdout.split("Overall:")[1].split("\n")[0]
        assert "EXPERIMENTAL" not in verdict_section
