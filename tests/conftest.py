"""Shared pytest fixtures for SafeCode tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path, monkeypatch):
    """Keep tests from reading or writing a developer's real user state."""
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "isolated-user-config.toml"))
    anchor_dir = tmp_path.parent / f"{tmp_path.name}-audit-anchors"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    approval_dir = tmp_path.parent / f"{tmp_path.name}-hook-approvals"
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(approval_dir))
    monkeypatch.setenv("SAFECODE_SHELL_HISTORY", str(tmp_path / "shell-history"))
    monkeypatch.setenv("SAFECODE_DISABLE_KEYCHAIN", "1")
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
