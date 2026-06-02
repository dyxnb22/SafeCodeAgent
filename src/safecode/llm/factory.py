"""Create LLM clients from SafeCode config."""

from safecode.config import SafeCodeConfig
from safecode.llm.base import LLMClient
from safecode.llm.mock import MockLLMClient
from safecode.llm.openai_client import OpenAICompatibleLLMClient

_ANTHROPIC_PROVIDERS = frozenset({"anthropic"})
_OPENAI_PROVIDERS = frozenset({"openai", "openai-compatible"})


def create_llm_client(config: SafeCodeConfig, *, session_id: str | None = None) -> LLMClient:
    """Return the configured LLM client.

    Supported provider keys: ``mock``, ``openai``, ``openai-compatible``, ``anthropic``.
    ``anthropic`` is experimental — provider behavior is not a stable contract.
    """
    if config.llm.provider == "mock":
        return MockLLMClient()
    if config.llm.provider in _OPENAI_PROVIDERS:
        return OpenAICompatibleLLMClient(config=config, session_id=session_id)
    if config.llm.provider in _ANTHROPIC_PROVIDERS:
        from safecode.llm.anthropic_client import AnthropicLLMClient
        return AnthropicLLMClient(config=config, session_id=session_id)
    raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")
