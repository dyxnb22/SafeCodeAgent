"""Tests for sac smoke live-provider (v4.10.4) — deterministic refusal tests only."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_smoke import _check_live_smoke_preconditions, run_live_provider_smoke

runner = CliRunner()


# ---------------------------------------------------------------------------
# Precondition refusal tests (all deterministic — no real network calls)
# ---------------------------------------------------------------------------


class TestLiveSmokeRefusals:
    def _make_config(
        self,
        provider: str = "deepseek",
        network_enabled: bool = True,
        allowlist: list | None = None,
    ):
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.llm.provider = provider
        cfg.llm.base_url = "https://api.deepseek.com"
        cfg.llm.model = "deepseek-v4-pro"
        cfg.sandbox.network_enabled = network_enabled
        cfg.sandbox.network_allowlist = allowlist or []
        return cfg

    def test_refuses_without_env_flag(self, tmp_path: Path) -> None:
        cfg = self._make_config()
        env = {k: v for k, v in os.environ.items() if k != "SAFECODE_LIVE_SMOKE"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert not allowed
        assert "SAFECODE_LIVE_SMOKE" in reason

    def test_refuses_with_mock_provider(self, tmp_path: Path) -> None:
        cfg = self._make_config(provider="mock")
        with (
            patch.dict(os.environ, {"SAFECODE_LIVE_SMOKE": "1"}, clear=False),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert not allowed
        assert "mock" in reason.lower()

    def test_refuses_when_network_disabled(self, tmp_path: Path) -> None:
        cfg = self._make_config(network_enabled=False)
        env = {k: v for k, v in os.environ.items()}
        env["SAFECODE_LIVE_SMOKE"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-test"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert not allowed
        assert "network" in reason.lower()

    def test_refuses_without_api_key(self, tmp_path: Path) -> None:
        cfg = self._make_config(network_enabled=True)
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY",
                                  "SAFECODE_LLM_API_KEY", "SAFECODE_LIVE_SMOKE")}
        clean_env["SAFECODE_LIVE_SMOKE"] = "1"
        with (
            patch.dict(os.environ, clean_env, clear=True),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert not allowed
        assert "key" in reason.lower() or "env" in reason.lower()

    def test_refuses_when_host_not_in_allowlist(self, tmp_path: Path) -> None:
        cfg = self._make_config(network_enabled=True, allowlist=["example.com"])
        env = {k: v for k, v in os.environ.items()}
        env["SAFECODE_LIVE_SMOKE"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-test"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert not allowed
        assert "allowlist" in reason.lower()

    def test_allows_when_all_preconditions_met(self, tmp_path: Path) -> None:
        cfg = self._make_config(network_enabled=True)
        env = {k: v for k, v in os.environ.items()}
        env["SAFECODE_LIVE_SMOKE"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-test"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert allowed
        assert "preconditions met" in reason

    def test_allows_api_key_from_user_config(self, tmp_path: Path) -> None:
        cfg = self._make_config(network_enabled=True)
        cfg.llm.api_key = "sk-from-user-config"
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY",
                                  "SAFECODE_LLM_API_KEY", "SAFECODE_LIVE_SMOKE")}
        clean_env["SAFECODE_LIVE_SMOKE"] = "1"
        with (
            patch.dict(os.environ, clean_env, clear=True),
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
        ):
            allowed, reason = _check_live_smoke_preconditions(tmp_path)
        assert allowed
        assert "preconditions met" in reason


# ---------------------------------------------------------------------------
# CLI surface tests (refusal path, no real network)
# ---------------------------------------------------------------------------


class TestLiveSmokeCliRefusal:
    def test_cli_exits_nonzero_without_env(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        env = {k: v for k, v in os.environ.items() if k != "SAFECODE_LIVE_SMOKE"}
        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(app, ["smoke", "live-provider"], catch_exceptions=False)
        assert result.exit_code != 0

    def test_cli_refusal_message_no_secret_leak(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        env = {k: v for k, v in os.environ.items()
               if k not in ("SAFECODE_LIVE_SMOKE", "DEEPSEEK_API_KEY")}
        env["DEEPSEEK_API_KEY"] = "sk-super-secret-xyz"
        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(app, ["smoke", "live-provider"], catch_exceptions=False)
        assert "sk-super-secret-xyz" not in result.output

    def test_cli_json_output_refused(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        env = {k: v for k, v in os.environ.items() if k != "SAFECODE_LIVE_SMOKE"}
        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(app, ["smoke", "live-provider", "--json"], catch_exceptions=False)
        assert result.exit_code != 0
        import json
        data = json.loads(result.output)
        assert data["status"] == "refused"
        assert data["data"]["allowed"] is False


# ---------------------------------------------------------------------------
# run_live_provider_smoke: mock the LLM client to verify behavior without network
# ---------------------------------------------------------------------------


class TestRunLiveSmokeNoNetwork:
    def _make_config(self, provider: str = "deepseek"):
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.llm.provider = provider
        cfg.llm.base_url = "https://api.deepseek.com"
        cfg.llm.model = "deepseek-v4-pro"
        cfg.sandbox.network_enabled = True
        return cfg

    def test_smoke_returns_ask_and_propose_patch_scenarios(self, tmp_path: Path) -> None:
        cfg = self._make_config()

        mock_client = MagicMock()
        mock_client.ask.return_value = MagicMock(content="4")
        mock_client.propose_patch.return_value = MagicMock(patch_text="*** Begin Patch\n*** End Patch")

        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
            patch("safecode.cli_smoke.create_llm_client", return_value=mock_client),
        ):
            result = run_live_provider_smoke(tmp_path)

        scenario_names = [s["scenario"] for s in result["scenarios"]]
        assert "ask" in scenario_names
        assert "propose_patch" in scenario_names

    def test_smoke_reports_provider_and_model(self, tmp_path: Path) -> None:
        cfg = self._make_config()

        mock_client = MagicMock()
        mock_client.ask.return_value = MagicMock(content="4")
        mock_client.propose_patch.return_value = MagicMock(patch_text="*** Begin Patch\n*** End Patch")

        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
            patch("safecode.cli_smoke.create_llm_client", return_value=mock_client),
        ):
            result = run_live_provider_smoke(tmp_path)

        assert result["provider"] == "deepseek"
        assert result["model"] == "deepseek-v4-pro"

    def test_smoke_never_applies_patch(self, tmp_path: Path) -> None:
        cfg = self._make_config()

        mock_client = MagicMock()
        mock_client.ask.return_value = MagicMock(content="4")
        mock_client.propose_patch.return_value = MagicMock(patch_text="*** Begin Patch\n*** End Patch")

        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
            patch("safecode.cli_smoke.create_llm_client", return_value=mock_client),
        ):
            result = run_live_provider_smoke(tmp_path)

        # No files were written to tmp_path (no apply, no source writes)
        written_files = list(tmp_path.rglob("*"))
        assert len(written_files) == 0

    def test_smoke_handles_ask_failure_gracefully(self, tmp_path: Path) -> None:
        cfg = self._make_config()

        mock_client = MagicMock()
        mock_client.ask.side_effect = RuntimeError("network down")
        mock_client.propose_patch.return_value = MagicMock(patch_text="*** Begin Patch\n*** End Patch")

        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
            patch("safecode.cli_smoke.create_llm_client", return_value=mock_client),
        ):
            result = run_live_provider_smoke(tmp_path)

        ask_scenario = next(s for s in result["scenarios"] if s["scenario"] == "ask")
        assert ask_scenario["passed"] is False
        assert result["all_passed"] is False

    def test_smoke_output_redacted(self, tmp_path: Path) -> None:
        """Scenario output must not contain raw secret values."""
        cfg = self._make_config()

        mock_client = MagicMock()
        mock_client.ask.return_value = MagicMock(content="answer with sk-secret-key inside")
        mock_client.propose_patch.return_value = MagicMock(patch_text="")

        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=cfg),
            patch("safecode.cli_smoke.create_llm_client", return_value=mock_client),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-secret-key"}),
        ):
            result = run_live_provider_smoke(tmp_path)

        # The raw API key value must not appear in scenario output
        for scenario in result["scenarios"]:
            for v in scenario.values():
                if isinstance(v, str):
                    assert "sk-secret-key" not in v
