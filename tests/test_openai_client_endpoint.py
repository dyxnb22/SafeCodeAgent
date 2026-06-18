"""Tests for OpenAICompatibleLLMClient endpoint normalization and key resolution (v4.10.0)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from safecode.llm.openai_client import _normalize_endpoint, OpenAICompatibleLLMClient
from safecode.config import SafeCodeConfig


# ---------------------------------------------------------------------------
# _normalize_endpoint
# ---------------------------------------------------------------------------


class TestNormalizeEndpoint:
    def test_bare_base_url_gets_v1_completions(self):
        assert _normalize_endpoint("https://api.deepseek.com") == (
            "https://api.deepseek.com/v1/chat/completions"
        )

    def test_base_url_with_v1_gets_chat_completions(self):
        assert _normalize_endpoint("https://api.deepseek.com/v1") == (
            "https://api.deepseek.com/v1/chat/completions"
        )

    def test_base_url_with_v1_slash_gets_chat_completions(self):
        assert _normalize_endpoint("https://api.deepseek.com/v1/") == (
            "https://api.deepseek.com/v1/chat/completions"
        )

    def test_full_url_not_double_appended(self):
        full = "https://api.openai.com/v1/chat/completions"
        assert _normalize_endpoint(full) == full

    def test_full_url_with_trailing_slash_not_double_appended(self):
        # trailing slash is stripped
        full = "https://api.openai.com/v1/chat/completions/"
        result = _normalize_endpoint(full)
        assert result == "https://api.openai.com/v1/chat/completions"
        assert result.count("/v1/chat/completions") == 1

    def test_custom_base_url_no_path(self):
        result = _normalize_endpoint("https://my-proxy.example.com")
        assert result == "https://my-proxy.example.com/v1/chat/completions"

    def test_idempotent_when_full_url_supplied(self):
        url = "https://api.openai.com/v1/chat/completions"
        assert _normalize_endpoint(_normalize_endpoint(url)) == _normalize_endpoint(url)


# ---------------------------------------------------------------------------
# OpenAICompatibleLLMClient API key resolution
# ---------------------------------------------------------------------------


class TestAPIKeyResolution:
    def _make_config(self, base_url: str = "https://api.deepseek.com") -> SafeCodeConfig:
        cfg = SafeCodeConfig()
        cfg.llm.model = "deepseek-v4-pro"
        cfg.llm.base_url = base_url
        cfg.sandbox.network_enabled = True
        return cfg

    def test_provider_env_var_takes_priority(self):
        cfg = self._make_config()
        env = {"DEEPSEEK_API_KEY": "sk-deepseek-key", "OPENAI_API_KEY": "sk-openai-key"}
        with patch.dict(os.environ, env, clear=False):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client.api_key == "sk-deepseek-key"

    def test_provider_env_var_takes_priority_over_keychain(self):
        cfg = self._make_config()
        env = {"DEEPSEEK_API_KEY": "sk-deepseek-key"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("safecode.security.keychain.get_api_key", return_value="sk-keychain"),
        ):
            client = OpenAICompatibleLLMClient(
                cfg,
                api_key_env="DEEPSEEK_API_KEY",
                keychain_provider="deepseek",
            )
        assert client.api_key == "sk-deepseek-key"

    def test_falls_back_to_provider_keychain(self):
        cfg = self._make_config()
        base = {k: v for k, v in os.environ.items()
                if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with (
            patch.dict(os.environ, base, clear=True),
            patch("safecode.security.keychain.get_api_key", return_value="sk-keychain"),
        ):
            client = OpenAICompatibleLLMClient(
                cfg,
                api_key_env="DEEPSEEK_API_KEY",
                keychain_provider="deepseek",
            )
        assert client.api_key == "sk-keychain"

    def test_provider_keychain_takes_priority_over_openai_fallback(self):
        cfg = self._make_config()
        env = {"OPENAI_API_KEY": "sk-openai-key"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("safecode.security.keychain.get_api_key", return_value="sk-keychain"),
        ):
            client = OpenAICompatibleLLMClient(
                cfg,
                api_key_env="DEEPSEEK_API_KEY",
                keychain_provider="deepseek",
            )
        assert client.api_key == "sk-keychain"

    def test_falls_back_to_openai_key(self):
        cfg = self._make_config()
        env = {"OPENAI_API_KEY": "sk-openai-key"}
        no_deep = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with patch.dict(os.environ, {**no_deep, "OPENAI_API_KEY": "sk-openai-key"}, clear=True):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client.api_key == "sk-openai-key"

    def test_falls_back_to_safecode_key(self):
        cfg = self._make_config()
        base = {k: v for k, v in os.environ.items()
                if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with patch.dict(os.environ, {**base, "SAFECODE_LLM_API_KEY": "sk-safecode"}, clear=True):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client.api_key == "sk-safecode"

    def test_missing_key_names_provider_env_var(self):
        cfg = self._make_config()
        empty = {k: v for k, v in os.environ.items()
                 if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with patch.dict(os.environ, empty, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert "DEEPSEEK_API_KEY" in str(exc_info.value)

    def test_secret_not_in_error_text(self):
        cfg = self._make_config()
        env = {"DEEPSEEK_API_KEY": "sk-super-secret-value"}
        with patch.dict(os.environ, env, clear=True):
            try:
                OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
            except RuntimeError as exc:
                assert "sk-super-secret-value" not in str(exc)

    def test_deepseek_base_url_normalized_to_completions(self):
        cfg = self._make_config(base_url="https://api.deepseek.com")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client.base_url == "https://api.deepseek.com/v1/chat/completions"

    def test_legacy_full_url_preserved(self):
        full_url = "https://api.openai.com/v1/chat/completions"
        cfg = self._make_config(base_url=full_url)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            client = OpenAICompatibleLLMClient(cfg)
        assert client.base_url == full_url
