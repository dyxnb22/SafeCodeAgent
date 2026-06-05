"""Tests for v4.17.0 streaming output (sac ask --stream and shell)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.llm.stream import StreamChunk, StreamResult, aggregate_chunks


class FakeStreamingClient:
    """Fake LLM client that implements stream_chat for deterministic tests."""

    def __init__(self, chunks: list[StreamChunk] | None = None) -> None:
        self._chunks = chunks or [
            StreamChunk(delta="Hello"),
            StreamChunk(delta=" from"),
            StreamChunk(delta=" streaming", finish_reason="stop"),
        ]

    def stream_chat(self, messages):
        yield from self._chunks

    def ask(self, question, context):
        return type("Answer", (), {"content": "Hello from batch"})

    def propose_patch(self, task, context):
        return type("Patch", (), {"patch_text": "mock patch"})


def test_aggregate_chunks():
    chunks = iter([
        StreamChunk(delta="Hello"),
        StreamChunk(delta=" World"),
        StreamChunk(delta="!", finish_reason="stop"),
    ])
    result = aggregate_chunks(chunks)
    assert result.text == "Hello World!"
    assert result.finish_reason == "stop"


def test_stream_chunk_dataclass():
    c = StreamChunk(delta="test", finish_reason="stop")
    assert c.delta == "test"
    assert c.finish_reason == "stop"


def test_stream_chunk_default():
    c = StreamChunk(delta="test")
    assert c.finish_reason is None


def test_orchestrator_ask_stream_yields_chunks(tmp_path: Path):
    """AgentOrchestrator.ask_stream yields redacted chunks from a streaming client."""
    fake = FakeStreamingClient()
    orch = AgentOrchestrator(tmp_path, llm_client=fake)
    chunks = list(orch.ask_stream("test question"))
    assert len(chunks) >= 1
    assert all(isinstance(c, StreamChunk) for c in chunks)
    full = "".join(c.delta for c in chunks)
    assert "Hello" in full
    assert "streaming" in full


def test_orchestrator_ask_stream_fallback_non_streaming(tmp_path: Path):
    """Falls back to batch when client does not support streaming."""

    class BatchOnlyClient:
        def ask(self, question, context):
            return type("Answer", (), {"content": "batch response"})()

    orch = AgentOrchestrator(tmp_path, llm_client=BatchOnlyClient())
    chunks = list(orch.ask_stream("test"))
    assert len(chunks) == 1
    assert chunks[0].delta == "batch response"
    assert chunks[0].finish_reason == "stop"


def test_stream_chunks_to_console_non_tty():
    """stream_chunks_to_console prints chunks without Rich in non-TTY mode."""
    from safecode.cli_stream import stream_chunks_to_console

    chunks = iter([
        StreamChunk(delta="Hello"),
        StreamChunk(delta=" World", finish_reason="stop"),
    ])
    with patch("builtins.print") as mock_print:
        result = stream_chunks_to_console(chunks, is_tty=False)
    assert result == "Hello World"
    assert mock_print.call_count >= 1


def test_render_stream_batch():
    """render_stream prints all chunks in non-TTY mode."""
    from safecode.cli_stream import render_stream

    fake = FakeStreamingClient()
    orch = AgentOrchestrator(Path("/tmp"), llm_client=fake)
    with patch("builtins.print"):
        result = render_stream(orch, "test", is_tty=False)
    assert "Hello" in result
    assert "streaming" in result


def test_router_ask_intent_stream(tmp_path: Path):
    """Shell router streams ask intents in TTY mode."""
    from safecode.shell_session.router import _handle_ask_intent_stream

    fake = FakeStreamingClient()
    with patch("safecode.agent.orchestrator.AgentOrchestrator") as mock_orch_cls:
        mock_orch = mock_orch_cls.return_value
        mock_orch.ask_stream.return_value = iter([
            StreamChunk(delta="Hello"),
            StreamChunk(delta=" from", finish_reason="stop"),
        ])
        with patch("builtins.print"):
            result = _handle_ask_intent_stream("what is this", tmp_path)
        assert "Hello" in result


def test_cli_stream_module_importable():
    """cli_stream module is importable and exports expected symbols."""
    from safecode import cli_stream
    assert hasattr(cli_stream, "render_stream")
    assert hasattr(cli_stream, "stream_chunks_to_console")
