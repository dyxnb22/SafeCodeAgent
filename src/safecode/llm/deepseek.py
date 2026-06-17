"""DeepSeek provider preset for SafeCode Agent.

This module defines static preset data for the DeepSeek provider.
It never makes network calls and never reads or writes secrets.
Secrets are resolved from environment variables at client construction time.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeepSeekPreset:
    """Static defaults for the DeepSeek provider."""

    base_url: str
    default_model: str
    fallback_model: str
    api_key_env: str


DEEPSEEK_PRESET = DeepSeekPreset(
    base_url="https://api.deepseek.com",
    default_model="deepseek-v4-flash",
    fallback_model="deepseek-v4-pro",
    api_key_env="DEEPSEEK_API_KEY",
)


def describe() -> dict:
    """Return a machine-readable description of the DeepSeek preset.

    Used by sac doctor for static provider diagnostics.
    Never performs a network request or reads env-var values.
    """
    return {
        "provider": "deepseek",
        "base_url": DEEPSEEK_PRESET.base_url,
        "default_model": DEEPSEEK_PRESET.default_model,
        "fallback_model": DEEPSEEK_PRESET.fallback_model,
        "api_key_env": DEEPSEEK_PRESET.api_key_env,
        "experimental": True,
        "note": (
            "DeepSeek is an EXPERIMENTAL provider preset. "
            "Set DEEPSEEK_API_KEY in the environment; never write it to disk."
        ),
    }
