"""Live provider smoke tests.

These are skipped unless SAFECODE_LIVE_TESTS=1. See conftest.py for the gate.
Real network calls are made; real API credentials must be present in the environment.
"""

from __future__ import annotations

import os

import pytest


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"Live test requires {name} to be set.")
    return value


class TestLiveOpenAIProvider:
    """Smoke tests for the OpenAI-compatible provider against a live endpoint."""

    def test_ask_returns_nonempty_answer(self) -> None:
        _require_env("OPENAI_API_KEY")
        from safecode.config import SafeCodeConfig
        from safecode.llm.openai_client import OpenAICompatibleLLMClient
        from unittest.mock import patch

        cfg = SafeCodeConfig()
        cfg.llm.provider = "openai-compatible"
        cfg.sandbox.network_enabled = True

        with patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"):
            client = OpenAICompatibleLLMClient(config=cfg)

        answer = client.ask("What is 1+1?", {})
        assert answer.content
        assert len(answer.content) > 0


class TestLiveAnthropicProvider:
    """Smoke tests for the Anthropic provider against a live endpoint."""

    def test_ask_returns_nonempty_answer(self) -> None:
        _require_env("ANTHROPIC_API_KEY")
        from safecode.config import SafeCodeConfig
        from safecode.llm.anthropic_client import AnthropicLLMClient
        from unittest.mock import patch

        cfg = SafeCodeConfig()
        cfg.llm.provider = "anthropic"
        cfg.llm.base_url = "https://api.anthropic.com/v1/messages"
        cfg.sandbox.network_enabled = True

        with patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"):
            client = AnthropicLLMClient(config=cfg)

        answer = client.ask("What is 1+1?", {})
        assert answer.content
        assert len(answer.content) > 0
