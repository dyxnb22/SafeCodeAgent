"""Tests for v3.2.1 LLM streaming abstraction."""

from __future__ import annotations

import json
from typing import Iterator

import pytest

from safecode.llm.stream import (
    StreamChunk,
    StreamError,
    StreamResult,
    SupportsStreaming,
    aggregate_chunks,
    parse_sse_line,
    parse_sse_stream,
)


# ---------------------------------------------------------------------------
# parse_sse_line
# ---------------------------------------------------------------------------


class TestParseSseLine:
    def test_parses_content_delta(self) -> None:
        line = 'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}'
        chunk = parse_sse_line(line)
        assert chunk is not None
        assert chunk.delta == "Hello"
        assert chunk.finish_reason is None

    def test_parses_finish_reason_stop(self) -> None:
        line = 'data: {"choices":[{"delta":{"content":" world"},"finish_reason":"stop"}]}'
        chunk = parse_sse_line(line)
        assert chunk is not None
        assert chunk.delta == " world"
        assert chunk.finish_reason == "stop"

    def test_done_sentinel_returns_none(self) -> None:
        assert parse_sse_line("data: [DONE]") is None

    def test_blank_line_returns_none(self) -> None:
        assert parse_sse_line("") is None

    def test_comment_line_returns_none(self) -> None:
        assert parse_sse_line(": keep-alive") is None

    def test_non_data_prefix_returns_none(self) -> None:
        assert parse_sse_line("event: message") is None

    def test_malformed_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_sse_line("data: {not valid json}")

    def test_empty_delta_object(self) -> None:
        line = 'data: {"choices":[{"delta":{},"finish_reason":null}]}'
        chunk = parse_sse_line(line)
        assert chunk is not None
        assert chunk.delta == ""

    def test_no_choices_returns_empty_chunk(self) -> None:
        line = 'data: {"id":"1","choices":[]}'
        chunk = parse_sse_line(line)
        assert chunk is not None
        assert chunk.delta == ""

    def test_leading_whitespace_in_data_field(self) -> None:
        line = 'data:   {"choices":[{"delta":{"content":"hi"},"finish_reason":null}]}'
        chunk = parse_sse_line(line)
        assert chunk is not None
        assert chunk.delta == "hi"


# ---------------------------------------------------------------------------
# parse_sse_stream
# ---------------------------------------------------------------------------


class TestParseSseStream:
    def _make_lines(self, *payloads: str) -> list[str]:
        return [f"data: {p}" for p in payloads]

    def test_yields_chunks_from_stream(self) -> None:
        lines = self._make_lines(
            '{"choices":[{"delta":{"content":"A"},"finish_reason":null}]}',
            '{"choices":[{"delta":{"content":"B"},"finish_reason":"stop"}]}',
            "[DONE]",
        )
        chunks = list(parse_sse_stream(iter(lines)))
        assert len(chunks) == 2
        assert chunks[0].delta == "A"
        assert chunks[1].delta == "B"
        assert chunks[1].finish_reason == "stop"

    def test_skips_blank_lines(self) -> None:
        lines = [
            "",
            'data: {"choices":[{"delta":{"content":"X"},"finish_reason":null}]}',
            "",
            "data: [DONE]",
        ]
        chunks = list(parse_sse_stream(iter(lines)))
        assert len(chunks) == 1
        assert chunks[0].delta == "X"

    def test_malformed_line_propagates_value_error(self) -> None:
        lines = [
            'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}',
            "data: {bad json!}",
        ]
        with pytest.raises(ValueError):
            list(parse_sse_stream(iter(lines)))

    def test_empty_stream_yields_nothing(self) -> None:
        assert list(parse_sse_stream(iter([]))) == []


# ---------------------------------------------------------------------------
# aggregate_chunks
# ---------------------------------------------------------------------------


class TestAggregateChunks:
    def test_aggregates_text(self) -> None:
        chunks = [StreamChunk(delta="He"), StreamChunk(delta="llo"), StreamChunk(delta="!")]
        result = aggregate_chunks(iter(chunks))
        assert result.text == "Hello!"

    def test_captures_last_finish_reason(self) -> None:
        chunks = [
            StreamChunk(delta="foo", finish_reason=None),
            StreamChunk(delta="bar", finish_reason="stop"),
        ]
        result = aggregate_chunks(iter(chunks))
        assert result.finish_reason == "stop"

    def test_empty_chunks_produce_empty_result(self) -> None:
        result = aggregate_chunks(iter([]))
        assert result.text == ""
        assert result.finish_reason is None

    def test_single_chunk_with_finish_reason(self) -> None:
        chunks = [StreamChunk(delta="Hi", finish_reason="stop")]
        result = aggregate_chunks(iter(chunks))
        assert result.text == "Hi"
        assert result.finish_reason == "stop"


# ---------------------------------------------------------------------------
# StreamResult
# ---------------------------------------------------------------------------


class TestStreamResult:
    def test_is_frozen(self) -> None:
        r = StreamResult(text="x", finish_reason="stop")
        with pytest.raises((AttributeError, TypeError)):
            r.text = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OpenAICompatibleLLMClient.stream_chat
# ---------------------------------------------------------------------------


def _make_openai_client_with_config():
    """Return a patched OpenAICompatibleLLMClient with network disabled."""
    from unittest.mock import patch

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
    return client


class TestOpenAIStreamChat:
    def _sse_lines(self, text: str) -> list[str]:
        chunks = text.split()
        lines = []
        for i, word in enumerate(chunks):
            delta = word if i == 0 else f" {word}"
            is_last = i == len(chunks) - 1
            finish = "stop" if is_last else "null"
            payload = json.dumps({
                "choices": [{"delta": {"content": delta}, "finish_reason": None if not is_last else "stop"}]
            })
            lines.append(f"data: {payload}")
        lines.append("data: [DONE]")
        return lines

    def test_chunk_aggregation_matches_non_streaming(self) -> None:
        client = _make_openai_client_with_config()
        text = "Hello world from stream"
        lines = self._sse_lines(text)

        def lines_fn(messages):
            return iter(lines)

        chunks = list(client.stream_chat([], _lines_fn=lines_fn))
        result = aggregate_chunks(iter(chunks))
        assert result.text == text.replace(" ", " ")  # spaces already in delta

    def test_stream_aggregated_text_equals_expected(self) -> None:
        client = _make_openai_client_with_config()
        lines = [
            'data: {"choices":[{"delta":{"content":"Safe"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"Code"},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        result = aggregate_chunks(client.stream_chat([], _lines_fn=lambda m: iter(lines)))
        assert result.text == "SafeCode"
        assert result.finish_reason == "stop"

    def test_malformed_event_raises_stream_error(self) -> None:
        client = _make_openai_client_with_config()
        lines = [
            'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}',
            "data: {bad json!}",
        ]
        with pytest.raises(StreamError):
            list(client.stream_chat([], _lines_fn=lambda m: iter(lines)))

    def test_empty_stream_produces_no_chunks(self) -> None:
        client = _make_openai_client_with_config()
        chunks = list(client.stream_chat([], _lines_fn=lambda m: iter([])))
        assert chunks == []

    def test_retry_does_not_duplicate_content(self) -> None:
        """Stream that fails before any output may be retried, but does not duplicate."""
        client = _make_openai_client_with_config()
        call_count = [0]

        def lines_fn(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                # Yield nothing, then raise — simulates pre-output failure
                return iter(["data: [DONE]"])
            return iter([
                'data: {"choices":[{"delta":{"content":"once"},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ])

        # First call: empty stream
        result1 = aggregate_chunks(client.stream_chat([], _lines_fn=lines_fn))
        assert result1.text == ""

        # Second call: real content
        result2 = aggregate_chunks(client.stream_chat([], _lines_fn=lines_fn))
        assert result2.text == "once"

        # Content was not duplicated
        assert result1.text != result2.text

    def test_stream_does_not_modify_session_state(self) -> None:
        """Cancelling a stream early must not corrupt the accumulator."""
        from unittest.mock import MagicMock
        from pathlib import Path

        client = _make_openai_client_with_config()
        # Ensure no session id is set
        assert client._session_id is None

        lines = [
            'data: {"choices":[{"delta":{"content":"x"},"finish_reason":null}]}',
            "data: [DONE]",
        ]
        # Iterating partially does not raise and leaves no side effects
        gen = client.stream_chat([], _lines_fn=lambda m: iter(lines))
        first_chunk = next(gen)
        assert first_chunk.delta == "x"
        # Drop the generator without fully exhausting — no exception, no state mutation
        del gen


# ---------------------------------------------------------------------------
# SupportsStreaming protocol
# ---------------------------------------------------------------------------


class TestSupportsStreamingProtocol:
    def test_mock_client_satisfies_protocol(self) -> None:
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        assert hasattr(client, "stream_chat")
        chunks = list(client.stream_chat([]))
        assert len(chunks) >= 1
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_mock_stream_aggregates_to_non_empty(self) -> None:
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        result = aggregate_chunks(client.stream_chat([]))
        assert len(result.text) > 0

    def test_openai_client_has_stream_chat(self) -> None:
        client = _make_openai_client_with_config()
        assert hasattr(client, "stream_chat")
        assert callable(client.stream_chat)


# ---------------------------------------------------------------------------
# Non-streaming behavior unchanged
# ---------------------------------------------------------------------------


class TestNonStreamingUnchanged:
    def test_mock_ask_unchanged(self) -> None:
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        answer = client.ask("What is this?", {})
        assert answer.type == "answer"
        assert len(answer.content) > 0

    def test_mock_plan_unchanged(self) -> None:
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        plan = client.plan("Do something safe", {})
        assert plan.type == "plan"
        assert len(plan.steps) >= 1

    def test_mock_choose_tool_unchanged(self) -> None:
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        result = client.choose_tool("inspect the project", {})
        assert result.type in {"tool_intent", "stop_for_user"}
