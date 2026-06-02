"""Tests for v3.2.4 provider fan-out config."""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.schemas import (
    AgentAnswer,
    AgentPlanResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
)
from safecode.llm.factory import FanOutLLMClient, create_llm_client, _log_fanout
from safecode.llm.mock import MockLLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client_that_raises(error: Exception):
    """Return a mock LLMClient whose methods all raise the given error."""
    m = MagicMock()
    m.ask.side_effect = error
    m.plan.side_effect = error
    m.choose_tool.side_effect = error
    m.propose_patch.side_effect = error
    return m


def _make_client_that_returns(answer: object):
    """Return a mock LLMClient whose methods all return answer."""
    m = MagicMock()
    m.ask.return_value = answer
    m.plan.return_value = answer
    m.choose_tool.return_value = answer
    m.propose_patch.return_value = answer
    return m


# ---------------------------------------------------------------------------
# FanOutLLMClient — no fallback
# ---------------------------------------------------------------------------


class TestFanOutNoFallback:
    def test_no_fallback_success_returns_primary(self) -> None:
        answer = AgentAnswer(content="hello")
        primary = _make_client_that_returns(answer)
        client = FanOutLLMClient(primary=primary)
        result = client.ask("q", {})
        assert result is answer
        primary.ask.assert_called_once_with("q", {})

    def test_no_fallback_runtime_error_propagates(self) -> None:
        primary = _make_client_that_raises(RuntimeError("network down"))
        client = FanOutLLMClient(primary=primary)
        with pytest.raises(RuntimeError, match="network down"):
            client.ask("q", {})

    def test_no_fallback_permission_error_propagates(self) -> None:
        primary = _make_client_that_raises(PermissionError("network disabled"))
        client = FanOutLLMClient(primary=primary)
        with pytest.raises(PermissionError):
            client.ask("q", {})

    def test_no_fallback_value_error_propagates(self) -> None:
        primary = _make_client_that_raises(ValueError("contract violation"))
        client = FanOutLLMClient(primary=primary)
        with pytest.raises(ValueError):
            client.plan("g", {})


# ---------------------------------------------------------------------------
# FanOutLLMClient — primary success
# ---------------------------------------------------------------------------


class TestFanOutPrimarySuccess:
    def test_primary_success_does_not_call_fallback(self) -> None:
        answer = AgentAnswer(content="ok")
        primary = _make_client_that_returns(answer)
        fallback = _make_client_that_returns(AgentAnswer(content="fallback"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        result = client.ask("q", {})
        assert result.content == "ok"
        fallback.ask.assert_not_called()

    def test_all_methods_use_primary_on_success(self) -> None:
        answer = AgentAnswer(content="primary")
        primary = _make_client_that_returns(answer)
        fallback = MagicMock()
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        client.ask("q", {})
        client.plan("g", {})
        client.choose_tool("g", {})
        client.propose_patch("t", {})

        assert fallback.ask.call_count == 0
        assert fallback.plan.call_count == 0
        assert fallback.choose_tool.call_count == 0
        assert fallback.propose_patch.call_count == 0


# ---------------------------------------------------------------------------
# FanOutLLMClient — hard provider failure routes to fallback
# ---------------------------------------------------------------------------


class TestFanOutFallbackRouting:
    def test_primary_runtime_error_routes_to_fallback(self) -> None:
        fallback_answer = AgentAnswer(content="from fallback")
        primary = _make_client_that_raises(RuntimeError("provider down"))
        fallback = _make_client_that_returns(fallback_answer)
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        result = client.ask("q", {})
        assert result.content == "from fallback"

    def test_fallback_called_for_all_methods_on_primary_failure(self) -> None:
        fallback_answer = AgentAnswer(content="fb")
        primary = _make_client_that_raises(RuntimeError("down"))
        fallback = _make_client_that_returns(fallback_answer)
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        client.ask("q", {})
        client.plan("g", {})
        client.choose_tool("g", {})
        client.propose_patch("t", {})

        assert fallback.ask.call_count == 1
        assert fallback.plan.call_count == 1
        assert fallback.choose_tool.call_count == 1
        assert fallback.propose_patch.call_count == 1

    def test_primary_failure_emits_runtime_warning(self) -> None:
        primary = _make_client_that_raises(RuntimeError("down"))
        fallback = _make_client_that_returns(AgentAnswer(content="ok"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.ask("q", {})

        assert any(
            issubclass(w.category, RuntimeWarning) and "fanout" in str(w.message).lower()
            for w in caught
        )

    def test_fallback_failure_fails_closed(self) -> None:
        primary = _make_client_that_raises(RuntimeError("primary down"))
        fallback = _make_client_that_raises(RuntimeError("fallback also down"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        with pytest.raises(RuntimeError, match="fallback also down"):
            client.ask("q", {})


# ---------------------------------------------------------------------------
# Safety: policy/network blocks do not route to fallback
# ---------------------------------------------------------------------------


class TestFanOutSafetyGates:
    def test_permission_error_not_routed_to_fallback(self) -> None:
        """Network policy block (PermissionError) must not be bypassed via fallback."""
        primary = _make_client_that_raises(PermissionError("network disabled by policy"))
        fallback = _make_client_that_returns(AgentAnswer(content="bypass"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        with pytest.raises(PermissionError):
            client.ask("q", {})
        fallback.ask.assert_not_called()

    def test_value_error_not_routed_to_fallback(self) -> None:
        """Hard contract violations (ValueError) must not be routed around."""
        primary = _make_client_that_raises(ValueError("hard contract violation"))
        fallback = _make_client_that_returns(AgentAnswer(content="bypass"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        with pytest.raises(ValueError):
            client.plan("g", {})
        fallback.plan.assert_not_called()

    def test_recoverable_contract_failure_not_routed(self) -> None:
        """RecoverableContractFailure returned as value is passed through, not routed."""
        rcf = RecoverableContractFailure(step=0, method="choose_tool", message="soft fail")
        primary = _make_client_that_returns(rcf)
        fallback = _make_client_that_returns(AgentAnswer(content="fallback answer"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        result = client.choose_tool("g", {})
        assert isinstance(result, RecoverableContractFailure)
        fallback.choose_tool.assert_not_called()


# ---------------------------------------------------------------------------
# Log redaction: warning must not contain prompt content
# ---------------------------------------------------------------------------


class TestFanOutLogRedaction:
    def test_warning_does_not_contain_prompt_text(self) -> None:
        secret_prompt = "SECRET_PASSWORD_ABC123"
        primary = _make_client_that_raises(RuntimeError("down"))
        fallback = _make_client_that_returns(AgentAnswer(content="ok"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.ask(secret_prompt, {"key": "value"})

        warning_texts = " ".join(str(w.message) for w in caught)
        assert secret_prompt not in warning_texts
        assert "SECRET" not in warning_texts

    def test_warning_contains_method_name(self) -> None:
        primary = _make_client_that_raises(RuntimeError("down"))
        fallback = _make_client_that_returns(AgentAnswer(content="ok"))
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.ask("q", {})

        assert any("ask" in str(w.message) for w in caught)

    def test_log_fanout_helper_does_not_include_exception_message(self) -> None:
        exc = RuntimeError("secret_token=xyz987")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _log_fanout("plan", exc)

        warning_texts = " ".join(str(w.message) for w in caught)
        # The type name appears but the exception message (containing secret) should not
        assert "RuntimeError" in warning_texts
        # The actual exception message is NOT included in the log
        assert "secret_token" not in warning_texts


# ---------------------------------------------------------------------------
# create_llm_client — factory behavior
# ---------------------------------------------------------------------------


class TestCreateLlmClientFanOut:
    def test_no_fallback_returns_single_client(self) -> None:
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.llm.provider = "mock"
        client = create_llm_client(cfg)
        assert isinstance(client, MockLLMClient)

    def test_fallback_configured_returns_fanout(self) -> None:
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.llm.provider = "mock"
        cfg.llm.fallback_provider = "mock"
        client = create_llm_client(cfg)
        assert isinstance(client, FanOutLLMClient)

    def test_fanout_primary_and_fallback_both_mock(self) -> None:
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.llm.provider = "mock"
        cfg.llm.fallback_provider = "mock"
        client = create_llm_client(cfg)
        assert isinstance(client, FanOutLLMClient)
        # Both primary and fallback should work
        result = client.ask("q", {})
        assert isinstance(result, AgentAnswer)

    def test_fallback_config_does_not_nest(self) -> None:
        """Fallback provider must not itself have a fallback (no infinite recursion)."""
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.llm.provider = "mock"
        cfg.llm.fallback_provider = "mock"
        client = create_llm_client(cfg)
        assert isinstance(client, FanOutLLMClient)
        # The fallback is a plain MockLLMClient, not another FanOutLLMClient
        assert isinstance(client._fallback, MockLLMClient)

    def test_fallback_network_policy_checked(self) -> None:
        """Both primary and fallback must pass network policy."""
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        cfg.llm.provider = "mock"
        cfg.llm.fallback_provider = "openai-compatible"
        cfg.llm.fallback_base_url = "http://localhost:9999/v1/chat/completions"

        policy_calls = []

        def mock_assert_allowed(url: str) -> None:
            policy_calls.append(url)

        with (
            patch("safecode.sandbox.network.NetworkPolicy.assert_allowed", side_effect=mock_assert_allowed),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            create_llm_client(cfg)

        assert any("localhost" in url for url in policy_calls)

    def test_default_provider_mock_unchanged(self) -> None:
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        assert cfg.llm.provider == "mock"
        assert cfg.llm.fallback_provider is None
        client = create_llm_client(cfg)
        assert isinstance(client, MockLLMClient)


# ---------------------------------------------------------------------------
# FanOutLLMClient — streaming proxy
# ---------------------------------------------------------------------------


class TestFanOutStreaming:
    def test_stream_chat_proxied_to_primary(self) -> None:
        from safecode.llm.stream import StreamChunk

        primary = MockLLMClient()  # has stream_chat
        fallback = MockLLMClient()
        client = FanOutLLMClient(primary=primary, fallback=fallback)

        chunks = list(client.stream_chat([]))
        assert len(chunks) >= 1
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_stream_chat_no_support_raises(self) -> None:
        primary = MagicMock(spec=["ask", "plan", "choose_tool", "propose_patch"])
        client = FanOutLLMClient(primary=primary)
        with pytest.raises(AttributeError):
            client.stream_chat([])
