"""Create LLM clients from SafeCode config."""

from __future__ import annotations

import warnings
from typing import Iterator

from safecode.config import SafeCodeConfig
from safecode.llm.base import LLMClient
from safecode.llm.mock import MockLLMClient
from safecode.llm.openai_client import OpenAICompatibleLLMClient

_ANTHROPIC_PROVIDERS = frozenset({"anthropic"})
_OPENAI_PROVIDERS = frozenset({"openai", "openai-compatible"})
_DEEPSEEK_PROVIDERS = frozenset({"deepseek"})


def create_llm_client(
    config: SafeCodeConfig,
    *,
    session_id: str | None = None,
    sac_dir: "Path | None" = None,
) -> LLMClient:
    """Return the configured LLM client.

    Supported provider keys: ``mock``, ``openai``, ``openai-compatible``, ``anthropic``.
    ``anthropic`` is experimental — provider behavior is not a stable contract.

    When ``config.llm.fallback_provider`` is set, returns a ``FanOutLLMClient`` that
    routes hard transport failures (``RuntimeError``) from the primary to the fallback.
    Both primary and fallback must pass network policy checks.

    v5.2.0: ``session_id`` + ``sac_dir`` enable per-session cost tracking via
    ``SessionCostAccumulator``.
    """
    primary = _create_single_client(config, session_id=session_id, sac_dir=sac_dir)
    if not config.llm.fallback_provider:
        return primary

    fallback_config = config.model_copy(deep=True)
    fallback_config.llm.provider = config.llm.fallback_provider
    if config.llm.fallback_model is not None:
        fallback_config.llm.model = config.llm.fallback_model
    if config.llm.fallback_base_url is not None:
        fallback_config.llm.base_url = config.llm.fallback_base_url
    # Clear fallback fields on the copy to avoid infinite nesting.
    fallback_config.llm.fallback_provider = None
    fallback_config.llm.fallback_model = None
    fallback_config.llm.fallback_base_url = None

    fallback = _create_single_client(fallback_config, session_id=session_id, sac_dir=sac_dir)
    return FanOutLLMClient(primary=primary, fallback=fallback)


def _create_single_client(
    config: SafeCodeConfig,
    *,
    session_id: str | None = None,
    sac_dir: "Path | None" = None,
) -> LLMClient:
    """Create one concrete LLM client from config.llm settings."""
    from pathlib import Path as _Path

    provider = config.llm.provider
    if provider == "mock":
        return MockLLMClient()
    if provider in _OPENAI_PROVIDERS:
        return OpenAICompatibleLLMClient(config=config, session_id=session_id, sac_dir=sac_dir)
    if provider in _DEEPSEEK_PROVIDERS:
        from safecode.llm.deepseek import DEEPSEEK_PRESET
        config = config.model_copy(deep=True)
        # Apply preset defaults only when user config is blank/default.
        _DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
        _DEFAULT_MODEL = "gpt-4.1-mini"
        if not config.llm.base_url or config.llm.base_url == _DEFAULT_BASE_URL:
            config.llm.base_url = DEEPSEEK_PRESET.base_url
        if not config.llm.model or config.llm.model == _DEFAULT_MODEL:
            config.llm.model = DEEPSEEK_PRESET.default_model
        return OpenAICompatibleLLMClient(
            config=config,
            session_id=session_id,
            sac_dir=sac_dir,
            api_key_env=DEEPSEEK_PRESET.api_key_env,
        )
    if provider in _ANTHROPIC_PROVIDERS:
        from safecode.llm.anthropic_client import AnthropicLLMClient
        return AnthropicLLMClient(config=config, session_id=session_id, sac_dir=sac_dir)
    raise ValueError(f"Unsupported LLM provider: {provider}")


class FanOutLLMClient:
    """Primary/fallback LLM router for hard transport failures.

    Delegates all LLMClient methods to the primary provider. On ``RuntimeError``
    (e.g. network errors, service unavailable) from the primary, logs a redacted
    warning and routes to the fallback.

    Does NOT route:
    - ``PermissionError``: network policy blocks must propagate, not be routed around.
    - ``ValueError``: hard contract violations remain fail-closed.
    - ``RecoverableContractFailure`` (returned value): handled by the agent loop.
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient | None = None) -> None:
        self._primary = primary
        self._fallback = fallback

    def ask(self, question: str, context: dict):
        return self._with_fallback("ask", question, context)

    def plan(self, goal: str, context: dict):
        return self._with_fallback("plan", goal, context)

    def choose_tool(self, goal: str, context: dict):
        return self._with_fallback("choose_tool", goal, context)

    def propose_patch(self, task: str, context: dict):
        return self._with_fallback("propose_patch", task, context)

    def stream_chat(self, messages: list[dict], **kwargs) -> Iterator:
        """Proxy streaming to the primary provider (no fan-out mid-stream)."""
        if hasattr(self._primary, "stream_chat"):
            return self._primary.stream_chat(messages, **kwargs)
        raise AttributeError("Primary provider does not support streaming.")

    def _with_fallback(self, method: str, *args):
        try:
            return getattr(self._primary, method)(*args)
        except RuntimeError as exc:
            if self._fallback is None:
                raise
            _log_fanout(method, exc)
            return getattr(self._fallback, method)(*args)


def _log_fanout(method: str, exc: Exception) -> None:
    """Emit a redacted warning on fallback routing without leaking prompts."""
    warnings.warn(
        f"[provider fanout] primary '{method}' failed ({type(exc).__name__}): routing to fallback",
        RuntimeWarning,
        stacklevel=4,
    )
