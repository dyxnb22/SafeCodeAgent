"""Tests for the DeepSeek provider preset (v4.10.0)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from safecode.config import LLMConfig, SafeCodeConfig
from safecode.llm.deepseek import DEEPSEEK_PRESET, describe


# ---------------------------------------------------------------------------
# Preset data
# ---------------------------------------------------------------------------


class TestDeepSeekPresetData:
    def test_base_url(self):
        assert DEEPSEEK_PRESET.base_url == "https://api.deepseek.com"

    def test_base_url_has_no_v1_suffix(self):
        # Endpoint normalization is the client's responsibility, not the preset's.
        assert not DEEPSEEK_PRESET.base_url.endswith("/v1")
        assert not DEEPSEEK_PRESET.base_url.endswith("/v1/chat/completions")

    def test_default_model(self):
        assert DEEPSEEK_PRESET.default_model == "deepseek-v4-pro"

    def test_fallback_model(self):
        assert DEEPSEEK_PRESET.fallback_model == "deepseek-v4-flash"

    def test_api_key_env(self):
        assert DEEPSEEK_PRESET.api_key_env == "DEEPSEEK_API_KEY"

    def test_describe_fields(self):
        d = describe()
        assert d["provider"] == "deepseek"
        assert d["base_url"] == DEEPSEEK_PRESET.base_url
        assert d["default_model"] == DEEPSEEK_PRESET.default_model
        assert d["api_key_env"] == DEEPSEEK_PRESET.api_key_env
        assert d["experimental"] is True

    def test_describe_no_secret(self):
        d = describe()
        assert "key" not in str(d.get("api_key_env", "")).lower() or "env" in str(d)
        # The describe output only contains the env var *name*, never the value.
        for v in d.values():
            if isinstance(v, str):
                assert "sk-" not in v


# ---------------------------------------------------------------------------
# Factory routing
# ---------------------------------------------------------------------------


class TestDeepSeekFactory:
    def _make_config(self, **llm_overrides) -> SafeCodeConfig:
        cfg = SafeCodeConfig()
        cfg.llm.provider = "deepseek"
        cfg.sandbox.network_enabled = True  # needed so NetworkPolicy passes
        for k, v in llm_overrides.items():
            setattr(cfg.llm, k, v)
        return cfg

    def test_factory_returns_openai_compatible_client(self):
        from safecode.llm.factory import _create_single_client
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = self._make_config()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deep"}):
            client = _create_single_client(cfg)
        assert isinstance(client, OpenAICompatibleLLMClient)

    def test_factory_applies_preset_base_url_when_default(self):
        from safecode.llm.factory import _create_single_client
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = self._make_config()
        # base_url is at LLMConfig default
        assert cfg.llm.base_url == "https://api.openai.com/v1/chat/completions"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deep"}):
            client = _create_single_client(cfg)
        # Client normalizes the preset base URL
        assert "deepseek" in client.base_url

    def test_factory_applies_preset_model_when_default(self):
        from safecode.llm.factory import _create_single_client

        cfg = self._make_config()
        assert cfg.llm.model == "gpt-4.1-mini"  # LLMConfig default
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deep"}):
            client = _create_single_client(cfg)
        assert client.model == "deepseek-v4-pro"

    def test_factory_respects_explicit_model_override(self):
        from safecode.llm.factory import _create_single_client

        cfg = self._make_config(model="deepseek-v4-flash")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deep"}):
            client = _create_single_client(cfg)
        assert client.model == "deepseek-v4-flash"

    def test_factory_respects_explicit_base_url_override(self):
        from safecode.llm.factory import _create_single_client

        cfg = self._make_config(base_url="https://custom.deepseek.example.com/v1")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deep"}):
            client = _create_single_client(cfg)
        assert "custom.deepseek.example.com" in client.base_url

    def test_missing_key_raises_runtime_error_naming_deepseek_env(self):
        from safecode.llm.factory import _create_single_client

        cfg = self._make_config()
        env = {k: v for k, v in os.environ.items()
               if k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                _create_single_client(cfg)
        assert "DEEPSEEK_API_KEY" in str(exc_info.value)

    def test_config_roundtrip_deepseek_provider(self):
        cfg = SafeCodeConfig()
        cfg.llm.provider = "deepseek"
        toml = cfg.to_toml()
        assert 'provider = "deepseek"' in toml


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


class TestDeepSeekConfigRoundTrip:
    def test_llm_config_accepts_deepseek(self):
        cfg = LLMConfig(provider="deepseek")
        assert cfg.provider == "deepseek"

    def test_safecode_config_deepseek_round_trips(self):
        cfg = SafeCodeConfig()
        cfg.llm.provider = "deepseek"
        cfg.llm.model = "deepseek-v4-pro"
        assert cfg.llm.provider == "deepseek"
        assert cfg.llm.model == "deepseek-v4-pro"
