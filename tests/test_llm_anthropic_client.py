"""Tests for v3.2.3 Anthropic provider."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from safecode.agent.schemas import (
    AgentAnswer,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
)
from safecode.llm.anthropic_client import (
    AnthropicLLMClient,
    _extract_text,
    _parse_anthropic_sse,
)
from safecode.llm.stream import StreamChunk, StreamError, aggregate_chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_anthropic_response(text: str, input_tokens: int = 10, output_tokens: int = 5) -> dict:
    """Build a minimal Anthropic Messages API response dict."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def _make_client(base_url: str = "http://localhost:9999/v1/messages") -> AnthropicLLMClient:
    from safecode.config import SafeCodeConfig

    cfg = SafeCodeConfig()
    cfg.llm.provider = "anthropic"
    cfg.llm.base_url = base_url

    with (
        patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
    ):
        return AnthropicLLMClient(config=cfg)


def _make_client_with_session(tmp_path: Path) -> AnthropicLLMClient:
    from safecode.config import SafeCodeConfig

    cfg = SafeCodeConfig()
    cfg.llm.provider = "anthropic"
    cfg.llm.base_url = "http://localhost:9999/v1/messages"

    with (
        patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
    ):
        return AnthropicLLMClient(config=cfg, session_id="sess-1", sac_dir=tmp_path)


# ---------------------------------------------------------------------------
# Factory selects anthropic
# ---------------------------------------------------------------------------


class TestFactory:
    def test_factory_creates_anthropic_client(self) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.llm.factory import create_llm_client
        from safecode.llm.anthropic_client import AnthropicLLMClient

        cfg = SafeCodeConfig()
        cfg.llm.provider = "anthropic"
        cfg.llm.base_url = "http://localhost/v1/messages"

        with (
            patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            client = create_llm_client(cfg)
        assert isinstance(client, AnthropicLLMClient)

    def test_factory_mock_unchanged(self) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.llm.factory import create_llm_client
        from safecode.llm.mock import MockLLMClient

        cfg = SafeCodeConfig()
        assert isinstance(create_llm_client(cfg), MockLLMClient)

    def test_factory_openai_unchanged(self) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.llm.factory import create_llm_client
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = SafeCodeConfig()
        cfg.llm.provider = "openai"
        cfg.llm.base_url = "http://localhost/v1/chat/completions"

        with (
            patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            client = create_llm_client(cfg)
        assert isinstance(client, OpenAICompatibleLLMClient)

    def test_factory_unsupported_raises(self) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.llm.factory import create_llm_client

        cfg = SafeCodeConfig()
        cfg.llm.provider = "unknown-provider"
        with pytest.raises(ValueError, match="Unsupported"):
            create_llm_client(cfg)

    def test_anthropic_requires_api_key(self) -> None:
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        cfg.llm.provider = "anthropic"
        cfg.llm.base_url = "http://localhost/v1/messages"

        with (
            patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
            patch.dict("os.environ", {}, clear=True),
        ):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                AnthropicLLMClient(config=cfg)


# ---------------------------------------------------------------------------
# _extract_text helper
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_extracts_text_from_content_list(self) -> None:
        data = _make_anthropic_response("hello world")
        assert _extract_text(data) == "hello world"

    def test_multiple_text_blocks_concatenated(self) -> None:
        data = {
            "content": [
                {"type": "text", "text": "foo"},
                {"type": "text", "text": "bar"},
            ]
        }
        assert _extract_text(data) == "foobar"

    def test_non_text_blocks_skipped(self) -> None:
        data = {
            "content": [
                {"type": "tool_use", "text": "should be ignored"},
                {"type": "text", "text": "kept"},
            ]
        }
        assert _extract_text(data) == "kept"

    def test_empty_content_list_returns_empty(self) -> None:
        assert _extract_text({"content": []}) == ""

    def test_missing_content_returns_empty(self) -> None:
        assert _extract_text({}) == ""


# ---------------------------------------------------------------------------
# Mocked successful response parses into agent contract
# ---------------------------------------------------------------------------


class TestAnthropicSuccessfulResponse:
    def _mock_messages(self, client: AnthropicLLMClient, text: str):
        """Patch _messages to return text."""
        return patch.object(client, "_messages", return_value=text)

    def test_ask_returns_agent_answer(self) -> None:
        client = _make_client()
        with self._mock_messages(client, "This is the answer."):
            result = client.ask("What?", {})
        assert isinstance(result, AgentAnswer)
        assert result.content == "This is the answer."

    def test_plan_parses_valid_plan(self) -> None:
        client = _make_client()
        plan_json = json.dumps({"type": "plan", "goal": "fix bug", "steps": ["check code", "apply fix"]})
        with self._mock_messages(client, plan_json):
            result = client.plan("fix bug", {})
        assert isinstance(result, AgentPlanResponse)
        assert result.goal == "fix bug"
        assert len(result.steps) == 2

    def test_choose_tool_parses_tool_intent(self) -> None:
        client = _make_client()
        intent_json = json.dumps({
            "type": "tool_intent",
            "intent": {"type": "read", "target": "main.py", "description": "inspect"},
            "rationale": "start with read",
        })
        with self._mock_messages(client, intent_json):
            result = client.choose_tool("goal", {})
        assert isinstance(result, AgentToolIntentResponse)

    def test_choose_tool_parses_stop_for_user(self) -> None:
        client = _make_client()
        stop_json = json.dumps({
            "type": "stop_for_user",
            "reason": "needs approval",
            "message": "Please review this.",
        })
        with self._mock_messages(client, stop_json):
            result = client.choose_tool("goal", {})
        assert isinstance(result, AgentStopForUserResponse)

    def test_propose_patch_returns_patch_response(self) -> None:
        client = _make_client()
        patch_text = "*** Begin Patch\n*** Update File: f.py\n@@\nSEARCH:\nold\nREPLACE:\nnew\n*** End Patch"
        with self._mock_messages(client, patch_text):
            result = client.propose_patch("fix it", {})
        from safecode.agent.schemas import AgentPatchResponse
        assert isinstance(result, AgentPatchResponse)
        assert result.patch_text == patch_text


# ---------------------------------------------------------------------------
# Mocked malformed response fails closed per v3.2.2 behaviour
# ---------------------------------------------------------------------------


class TestAnthropicMalformedResponse:
    def test_invalid_json_choose_tool_returns_recoverable(self) -> None:
        client = _make_client()
        with patch.object(client, "_messages", return_value="{not json}"):
            result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)

    def test_missing_type_choose_tool_returns_recoverable(self) -> None:
        client = _make_client()
        with patch.object(client, "_messages", return_value='{"content":"hi"}'):
            result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)

    def test_malformed_plan_raises_value_error(self) -> None:
        client = _make_client()
        with patch.object(client, "_messages", return_value="{bad}"):
            with pytest.raises(ValueError, match="validation"):
                client.plan("goal", {})

    def test_no_crash_on_empty_response(self) -> None:
        client = _make_client()
        with patch.object(client, "_messages", return_value=""):
            result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)


# ---------------------------------------------------------------------------
# Retry path reuses shared retry logic
# ---------------------------------------------------------------------------


class TestAnthropicRetry:
    def test_retry_on_429(self) -> None:
        """Verify that 429 responses trigger retry via retry_call."""
        client = _make_client()
        call_count = [0]

        def fake_urlopen(request, timeout=None):
            call_count[0] += 1
            if call_count[0] < 3:
                err = urllib.error.HTTPError(
                    url="", code=429, msg="Too Many Requests", hdrs=MagicMock(get=lambda k, d="": ""), fp=None
                )
                raise err
            # Third attempt succeeds
            response = MagicMock()
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            response.read.return_value = json.dumps(_make_anthropic_response("ok")).encode()
            return response

        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            patch("time.sleep"),
        ):
            result = client.ask("question", {})
        assert isinstance(result, AgentAnswer)
        assert call_count[0] == 3

    def test_no_retry_on_400(self) -> None:
        """Non-retryable 4xx errors propagate without retrying (wrapped as RuntimeError)."""
        client = _make_client()
        call_count = [0]

        def fake_urlopen(request, timeout=None):
            call_count[0] += 1
            raise urllib.error.HTTPError(
                url="", code=400, msg="Bad Request", hdrs=MagicMock(get=lambda k, d="": ""), fp=None
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises((urllib.error.HTTPError, RuntimeError)):
                client.ask("question", {})
        # Should only have been called once — no retry for 400
        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# Cost accounting records usage when mocked usage metadata exists
# ---------------------------------------------------------------------------


class TestAnthropicCostAccounting:
    def test_usage_recorded_to_cost_json(self, tmp_path: Path) -> None:
        client = _make_client_with_session(tmp_path)
        response_data = _make_anthropic_response("hello", input_tokens=20, output_tokens=10)

        def fake_urlopen(request, timeout=None):
            response = MagicMock()
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            response.read.return_value = json.dumps(response_data).encode()
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.ask("question", {})

        from safecode.llm.cost import SessionCostAccumulator
        total = SessionCostAccumulator(tmp_path, "sess-1").total()
        assert total.prompt_tokens == 20
        assert total.completion_tokens == 10
        assert total.total_tokens == 30

    def test_no_usage_no_file_written(self, tmp_path: Path) -> None:
        client = _make_client_with_session(tmp_path)
        response_data = {"content": [{"type": "text", "text": "hi"}]}  # no usage field

        def fake_urlopen(request, timeout=None):
            response = MagicMock()
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            response.read.return_value = json.dumps(response_data).encode()
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.ask("question", {})

        cost_path = tmp_path / "sessions" / "sess-1" / "cost.json"
        assert not cost_path.exists()


# ---------------------------------------------------------------------------
# Streaming path
# ---------------------------------------------------------------------------


class TestAnthropicStreaming:
    def _make_sse_lines(self, text: str) -> list[str]:
        lines = [
            'event: message_start',
            'data: {"type":"message_start","message":{"id":"msg_1","type":"message"}}',
            '',
            'event: content_block_start',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            '',
        ]
        for i, char in enumerate(text):
            lines += [
                'event: content_block_delta',
                f'data: {{"type":"content_block_delta","index":0,"delta":{{"type":"text_delta","text":{json.dumps(char)}}}}}',
                '',
            ]
        lines += [
            'event: message_delta',
            'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
            '',
            'event: message_stop',
            'data: {"type":"message_stop"}',
        ]
        return lines

    def test_stream_chat_yields_chunks(self) -> None:
        client = _make_client()
        lines = self._make_sse_lines("hi")
        chunks = list(client.stream_chat([], _lines_fn=lambda m: iter(lines)))
        # Should have content chunks plus a finish chunk
        content_chunks = [c for c in chunks if c.delta]
        assert len(content_chunks) == 2  # "h" and "i"

    def test_stream_aggregated_text(self) -> None:
        client = _make_client()
        lines = self._make_sse_lines("Hello")
        result = aggregate_chunks(client.stream_chat([], _lines_fn=lambda m: iter(lines)))
        assert result.text == "Hello"

    def test_malformed_stream_event_raises_stream_error(self) -> None:
        client = _make_client()
        lines = ["data: {bad json!}"]
        with pytest.raises(StreamError):
            list(client.stream_chat([], _lines_fn=lambda m: iter(lines)))

    def test_empty_stream_produces_no_chunks(self) -> None:
        client = _make_client()
        chunks = list(client.stream_chat([], _lines_fn=lambda m: iter([])))
        # Only finish chunks with empty delta are allowed
        content_chunks = [c for c in chunks if c.delta]
        assert content_chunks == []


# ---------------------------------------------------------------------------
# Network policy remains enforced
# ---------------------------------------------------------------------------


class TestAnthropicNetworkPolicy:
    def test_network_policy_checked_on_init(self) -> None:
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        cfg.llm.provider = "anthropic"
        cfg.llm.base_url = "https://api.anthropic.com/v1/messages"

        called = []

        def mock_assert_allowed(url: str) -> None:
            called.append(url)

        with (
            patch("safecode.sandbox.network.NetworkPolicy.assert_allowed", side_effect=mock_assert_allowed),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            AnthropicLLMClient(config=cfg)

        assert len(called) == 1
        assert "anthropic.com" in called[0]

    def test_network_policy_block_raises(self) -> None:
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        cfg.llm.provider = "anthropic"
        cfg.llm.base_url = "https://api.anthropic.com/v1/messages"

        with (
            patch(
                "safecode.sandbox.network.NetworkPolicy.assert_allowed",
                side_effect=PermissionError("Network disabled"),
            ),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(PermissionError):
                AnthropicLLMClient(config=cfg)


# ---------------------------------------------------------------------------
# OpenAI-compatible provider behavior must not regress
# ---------------------------------------------------------------------------


class TestOpenAINotRegressed:
    def test_openai_ask_still_works(self) -> None:
        from safecode.config import SafeCodeConfig
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = SafeCodeConfig()
        cfg.llm.provider = "openai-compatible"
        cfg.llm.base_url = "http://localhost:9999/v1/chat/completions"

        with (
            patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            client = OpenAICompatibleLLMClient(config=cfg)

        openai_response = {
            "choices": [{"message": {"content": "hello"}}],
        }

        def fake_urlopen(request, timeout=None):
            response = MagicMock()
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            response.read.return_value = json.dumps(openai_response).encode()
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.ask("question", {})
        assert isinstance(result, AgentAnswer)
        assert result.content == "hello"
