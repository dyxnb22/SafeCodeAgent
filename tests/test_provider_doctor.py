"""Tests for provider diagnostics in sac doctor (v4.10.2)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from safecode.config import SafeCodeConfig
from safecode.core.diagnostic import DiagnosticStatus
from safecode.doctor import Doctor


def _make_config(
    provider: str = "mock",
    model: str = "gpt-4.1-mini",
    base_url: str = "https://api.openai.com/v1/chat/completions",
    network_enabled: bool = False,
    allowlist: list | None = None,
) -> SafeCodeConfig:
    cfg = SafeCodeConfig()
    cfg.llm.provider = provider
    cfg.llm.model = model
    cfg.llm.base_url = base_url
    cfg.sandbox.network_enabled = network_enabled
    cfg.sandbox.network_allowlist = allowlist or []
    return cfg


class TestProviderDiagnosticsNoNetworkCall:
    """The provider section must never make an outbound HTTP request."""

    def test_urlopen_never_called_in_provider_section(self, tmp_path: Path) -> None:
        """Patch urlopen globally and assert it's not called during provider diagnostics."""
        config = _make_config(provider="deepseek", network_enabled=True)
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            with patch("urllib.request.urlopen") as mock_urlopen:
                # Isolate only the provider diagnostics method
                diagnostics = doctor._provider_diagnostics()
        mock_urlopen.assert_not_called()
        assert len(diagnostics) > 0

    def test_provider_name_diagnostic_present(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        names = [d.name for d in diagnostics]
        assert "provider_name" in names

    def test_provider_api_key_diagnostic_present(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        names = [d.name for d in diagnostics]
        assert "provider_api_key" in names

    def test_provider_base_url_diagnostic_present(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        names = [d.name for d in diagnostics]
        assert "provider_base_url" in names

    def test_provider_model_diagnostic_present(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        names = [d.name for d in diagnostics]
        assert "provider_model" in names

    def test_provider_network_policy_diagnostic_present(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        names = [d.name for d in diagnostics]
        assert "provider_network_policy" in names


class TestMockProviderDiagnostics:
    def test_mock_provider_api_key_is_pass(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_api_key"].status == DiagnosticStatus.PASS

    def test_mock_provider_network_policy_is_pass(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock", network_enabled=False)
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_network_policy"].status == DiagnosticStatus.PASS

    def test_mock_provider_message_says_deterministic(self, tmp_path: Path) -> None:
        config = _make_config(provider="mock")
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert "deterministic" in diagnostics["provider_api_key"].message.lower()


class TestDeepSeekProviderDiagnostics:
    def test_deepseek_key_present_is_pass(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=True,
        )
        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=config),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=False),
        ):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_api_key"].status == DiagnosticStatus.PASS

    def test_deepseek_key_from_user_config_is_pass_without_leaking_secret(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=True,
        )
        config.llm.api_key = "sk-from-user-config"
        env = {k: v for k, v in os.environ.items()
               if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=config),
            patch.dict(os.environ, env, clear=True),
        ):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        api_key_diagnostic = {d.name: d for d in diagnostics}["provider_api_key"]
        all_messages = " ".join(d.message for d in diagnostics)
        assert api_key_diagnostic.status == DiagnosticStatus.PASS
        assert "trusted user config" in api_key_diagnostic.message
        assert "sk-from-user-config" not in all_messages

    def test_deepseek_key_missing_is_fail(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=True,
        )
        env = {k: v for k, v in os.environ.items()
               if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=config),
            patch.dict(os.environ, env, clear=True),
        ):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_api_key"].status == DiagnosticStatus.FAIL

    def test_deepseek_key_missing_message_names_deepseek_env(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=True,
        )
        env = {k: v for k, v in os.environ.items()
               if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=config),
            patch.dict(os.environ, env, clear=True),
        ):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert "DEEPSEEK_API_KEY" in diagnostics["provider_api_key"].message

    def test_secrets_never_appear_in_diagnostic_messages(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=True,
        )
        with (
            patch("safecode.config.SafeCodeConfig.load", return_value=config),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-super-secret-9999"}, clear=False),
        ):
            doctor = Doctor(tmp_path)
            diagnostics = doctor._provider_diagnostics()
        all_messages = " ".join(d.message for d in diagnostics)
        assert "sk-super-secret-9999" not in all_messages

    def test_deepseek_network_disabled_is_fail(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=False,
        )
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_network_policy"].status == DiagnosticStatus.FAIL

    def test_deepseek_network_enabled_is_pass(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            network_enabled=True,
        )
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_network_policy"].status == DiagnosticStatus.PASS

    def test_malformed_base_url_is_fail(self, tmp_path: Path) -> None:
        config = _make_config(
            provider="deepseek",
            base_url="not-a-url",
            network_enabled=True,
        )
        with patch("safecode.config.SafeCodeConfig.load", return_value=config):
            doctor = Doctor(tmp_path)
            diagnostics = {d.name: d for d in doctor._provider_diagnostics()}
        assert diagnostics["provider_base_url"].status == DiagnosticStatus.FAIL


class TestUpdateCheckKnob:
    def test_update_check_skipped_when_env_zero(self, tmp_path: Path) -> None:
        doctor = Doctor(tmp_path, fetch_latest_version=lambda: "99.0.0")
        with patch.dict(os.environ, {"SAFECODE_DOCTOR_UPDATE_CHECK": "0"}):
            diag = doctor._update_check_diagnostic()
        assert diag.status == DiagnosticStatus.SKIP
        assert "SAFECODE_DOCTOR_UPDATE_CHECK=0" in diag.message

    def test_update_check_runs_when_env_one(self, tmp_path: Path) -> None:
        doctor = Doctor(tmp_path, fetch_latest_version=lambda: None)
        with patch.dict(os.environ, {"SAFECODE_DOCTOR_UPDATE_CHECK": "1"}):
            diag = doctor._update_check_diagnostic()
        # Returns SKIP on network failure (fetch returns None), not FAIL
        assert diag.status == DiagnosticStatus.SKIP

    def test_update_check_runs_by_default(self, tmp_path: Path) -> None:
        doctor = Doctor(tmp_path, fetch_latest_version=lambda: None)
        env = {k: v for k, v in os.environ.items() if k != "SAFECODE_DOCTOR_UPDATE_CHECK"}
        with patch.dict(os.environ, env, clear=True):
            diag = doctor._update_check_diagnostic()
        assert diag.name == "update_check"
