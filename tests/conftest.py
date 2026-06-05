"""Shared pytest fixtures for SafeCode tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path, monkeypatch):
    """Keep tests from reading a developer's real ~/.safecode/config.toml."""
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "isolated-user-config.toml"))
    import os
    if os.getenv("SAFECODE_LIVE_TESTS") != "1" and os.getenv("SAFECODE_LIVE_SMOKE") != "1":
        for name in (
            "SAFECODE_LLM_PROVIDER",
            "SAFECODE_LLM_MODEL",
            "SAFECODE_LLM_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(name, raising=False)
