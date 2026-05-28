"""Create LLM clients from SafeCode config."""

from safecode.config import SafeCodeConfig
from safecode.llm.base import LLMClient
from safecode.llm.mock import MockLLMClient
from safecode.llm.openai_client import OpenAICompatibleLLMClient


def create_llm_client(config: SafeCodeConfig) -> LLMClient:
    """Return the configured LLM client."""
    if config.llm.provider == "mock":
        return MockLLMClient()
    if config.llm.provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleLLMClient(config=config)
    raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")
