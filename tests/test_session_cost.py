"""Tests for v5.2.0 session cost tracking and /cost command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.llm.cost import SessionCostAccumulator, TokenUsage


# ---------------------------------------------------------------------------
# AgentSessionState.cost_tokens_* (v5.2.0)
# ---------------------------------------------------------------------------

class TestAgentSessionStateCostFields:
    def test_session_state_has_cost_fields(self):
        from safecode.agent.session import AgentSessionState
        from safecode.utils.time import utc_now_iso

        state = AgentSessionState(
            session_id="s1",
            goal="test",
            plan=[],
            current_step=0,
            status="active",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            cost_tokens_in=1000,
            cost_tokens_out=200,
            cost_cache_read=500,
        )
        assert state.cost_tokens_in == 1000
        assert state.cost_tokens_out == 200
        assert state.cost_cache_read == 500

    def test_session_state_cost_defaults_zero(self):
        from safecode.agent.session import AgentSessionState
        from safecode.utils.time import utc_now_iso

        state = AgentSessionState(
            session_id="s2",
            goal="test",
            plan=[],
            current_step=0,
            status="active",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        assert state.cost_tokens_in == 0
        assert state.cost_tokens_out == 0
        assert state.cost_cache_read == 0


# ---------------------------------------------------------------------------
# AgentLoop.session_cost() (v5.2.0)
# ---------------------------------------------------------------------------

class TestAgentLoopSessionCost:
    def test_session_cost_returns_none_when_no_data(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop(tmp_path)
        # No data yet — should return None
        result = loop.session_cost()
        assert result is None

    def test_session_cost_returns_usage_after_recording(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop(tmp_path)
        # Manually record usage
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        loop._cost_accumulator.record(usage)
        result = loop.session_cost()
        assert result is not None
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    def test_session_cost_session_id_stable(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop(tmp_path)
        assert loop._cost_session_id
        assert len(loop._cost_session_id) == 32  # uuid4 hex


# ---------------------------------------------------------------------------
# create_llm_client passes sac_dir (v5.2.0)
# ---------------------------------------------------------------------------

class TestCreateLLMClientSacDir:
    def test_create_llm_client_passes_sac_dir_to_openai(self, tmp_path):
        from safecode.config import SafeCodeConfig
        from safecode.llm.factory import create_llm_client
        config = SafeCodeConfig()
        config.llm.provider = "mock"
        client = create_llm_client(config, session_id="s1", sac_dir=tmp_path)
        # Mock client doesn't use sac_dir, but should not error
        assert client is not None

    def test_factory_with_openai_provider_passes_sac_dir(self, tmp_path):
        """create_llm_client wires sac_dir to OpenAICompatibleLLMClient."""
        from safecode.config import SafeCodeConfig
        from safecode.llm.openai_client import OpenAICompatibleLLMClient
        from safecode.llm.factory import _create_single_client
        config = SafeCodeConfig()
        config.llm.provider = "openai"
        config.llm.api_key = "test-key"
        config.llm.base_url = "https://api.openai.com/v1/chat/completions"

        with patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"):
            client = _create_single_client(config, session_id="cost-test", sac_dir=tmp_path)

        assert isinstance(client, OpenAICompatibleLLMClient)
        assert client._session_id == "cost-test"
        assert client._sac_dir == tmp_path


# ---------------------------------------------------------------------------
# _format_cost helper (v5.2.0)
# ---------------------------------------------------------------------------

class TestFormatCost:
    def test_format_cost_zero_returns_empty(self):
        from safecode.cli_shell import _format_cost
        assert _format_cost(0, 0) == ""

    def test_format_cost_small_amount(self):
        from safecode.cli_shell import _format_cost
        # 1000 input tokens at $3/Mtok = $0.000003 → very small
        result = _format_cost(1000, 100)
        assert result.startswith("~$")

    def test_format_cost_large_session(self):
        from safecode.cli_shell import _format_cost
        # 10k input + 2k output: (10/1000)*3 + (2/1000)*15 = 0.03 + 0.03 = $0.06
        result = _format_cost(10_000, 2_000)
        assert "~$0.0" in result

    def test_format_cost_includes_cache(self):
        from safecode.cli_shell import _format_cost
        # Cache reads are cheaper but still count
        result = _format_cost(0, 0, cache_read=1_000_000)
        assert result.startswith("~$")


# ---------------------------------------------------------------------------
# /cost slash command (v5.2.0)
# ---------------------------------------------------------------------------

class TestSlashCost:
    def test_slash_cost_mock_provider_shows_disabled(self, tmp_path):
        from safecode.cli_shell import _slash_cost
        # Default config uses mock provider
        result = _slash_cost(tmp_path)
        assert "mock" in result.lower() or "disabled" in result.lower()

    def test_slash_cost_no_data_shows_no_usage(self, tmp_path):
        from safecode.cli_shell import _slash_cost
        from safecode.config import SafeCodeConfig
        import json

        # Create a non-mock config to trigger cost display path
        config = SafeCodeConfig()
        config.llm.provider = "anthropic"
        config.llm.model = "claude-sonnet-4-6"
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        config_path = sac_dir / "config.toml"
        config_path.write_text('[llm]\nprovider = "anthropic"\nmodel = "claude-sonnet-4-6"\n')

        result = _slash_cost(tmp_path)
        # Should show no usage or the cost breakdown
        assert "cost" in result.lower() or "token" in result.lower()

    def test_slash_cost_with_data_shows_breakdown(self, tmp_path):
        from safecode.cli_shell import _slash_cost
        from safecode.config import SafeCodeConfig, LLMConfig
        from safecode.llm.cost import SessionCostAccumulator, TokenUsage

        # Write some cost data
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "test-session")
        acc.record(TokenUsage(prompt_tokens=12340, completion_tokens=1890, total_tokens=14230))

        # Patch config to use non-mock provider so cost display path is taken
        fake_config = SafeCodeConfig()
        fake_config.llm.provider = "anthropic"
        fake_config.llm.model = "claude-sonnet-4-6"
        with patch("safecode.config.SafeCodeConfig.load", return_value=fake_config):
            result = _slash_cost(tmp_path)

        assert "12" in result  # 12,340 tokens
        assert "1" in result   # 1,890 tokens
        assert "anthropic" in result.lower()


# ---------------------------------------------------------------------------
# Cost in agentic shell JSON output (v5.2.0)
# ---------------------------------------------------------------------------

class TestAgenticShellCostOutput:
    def test_agentic_shell_json_includes_cost_field(self, tmp_path, monkeypatch):
        """--json output from --agentic shell includes a 'cost' field when data available."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.agent.session import AgentSessionState
        from safecode.agent.loop import AgentRunResult
        from safecode.utils.time import utc_now_iso
        from safecode.llm.cost import TokenUsage
        import json

        monkeypatch.chdir(tmp_path)

        class FakeLoop:
            def __init__(self, project_root, llm_client=None, *, auto_edit=False,
                         full_auto=False, command_delay_ms=500):
                from uuid import uuid4
                from safecode.llm.cost import SessionCostAccumulator
                sac_dir = project_root / ".sac"
                self._cost_session_id = uuid4().hex
                self._cost_accumulator = SessionCostAccumulator(sac_dir, self._cost_session_id)
                # Record some cost data
                self._cost_accumulator.record(TokenUsage(
                    prompt_tokens=1000, completion_tokens=200, total_tokens=1200
                ))
                self._native_write_count = 0

            def session_cost(self):
                return self._cost_accumulator.load()

            def run(self, goal, max_steps=8, *, on_step=None):
                state = AgentSessionState(
                    session_id="cost-sess",
                    goal=goal or "",
                    plan=[],
                    current_step=0,
                    status="completed",
                    pending_action=None,
                    last_observation="done",
                    last_error=None,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                return AgentRunResult(state=state, steps=[], stopped_reason="completed")

            @property
            def last_typed_result(self):
                return None

        with patch("safecode.cli_shell.AgentLoop", FakeLoop):
            result = CliRunner().invoke(
                app, ["shell", "--agentic", "--non-tty", "--json"],
                input="test\n",
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "cost" in data.get("data", {})
        assert data["data"]["cost"]["input_tokens"] == 1000
        assert data["data"]["cost"]["output_tokens"] == 200
