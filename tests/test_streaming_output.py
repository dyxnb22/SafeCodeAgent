"""Tests for v4.17.0 streaming output (sac ask --stream and shell)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_keyboard_interrupt_midstream_not_swallowed() -> None:
    """KeyboardInterrupt raised inside render_stream is not silently swallowed.

    render_stream only catches ImportError (when Rich is unavailable); it does
    NOT catch KeyboardInterrupt. This test confirms the interrupt propagates so
    that the caller can handle it (e.g., with a non-zero exit code).
    """
    from safecode.cli_stream import render_stream

    def _interrupting_stream():
        yield StreamChunk(delta="Hello")
        raise KeyboardInterrupt

    class InterruptingClient:
        def stream_chat(self, messages):
            yield from _interrupting_stream()

        def ask(self, question, context):
            return type("Answer", (), {"content": "batch"})()

        def propose_patch(self, task, context):
            return type("Patch", (), {"patch_text": "mock patch"})()

    orch = AgentOrchestrator(Path("/tmp"), llm_client=InterruptingClient())

    with patch("builtins.print"):
        with pytest.raises(KeyboardInterrupt):
            render_stream(orch, "test", is_tty=False)


def test_keyboard_interrupt_midstream_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt from render_stream propagates as non-zero CLI exit.

    The `ask` command wraps render_stream in `except Exception`, which does NOT
    catch KeyboardInterrupt. We force the streaming branch by patching the
    `sys` module inside `cli_core` (CliRunner overrides sys.stdin/stdout during
    invoke, making a direct isatty patch ineffective).
    """
    import safecode.cli_core as cli_core_module
    from typer.testing import CliRunner as TRunner
    from safecode.cli import app

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".sac" / "config.toml").write_text(
        '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
        'base_url = "http://localhost:8080/v1"\n'
        "[sandbox]\nnetwork_enabled = false\n",
        encoding="utf-8",
    )

    cli_runner = TRunner()

    # Patch sys inside cli_core so is_tty evaluates True during the test.
    import sys as _sys
    mock_sys = MagicMock()
    mock_sys.stdin.isatty.return_value = True
    mock_sys.stdout.isatty.return_value = True
    # Preserve other sys attributes the CLI relies on (e.g. argv, path)
    mock_sys.argv = _sys.argv
    mock_sys.path = _sys.path

    with patch.object(cli_core_module, "sys", mock_sys), \
         patch("safecode.cli_stream.render_stream", side_effect=KeyboardInterrupt):
        result = cli_runner.invoke(app, ["ask", "--stream", "hello"])

    # The CLI must not exit with code 0 after a KeyboardInterrupt mid-stream.
    assert result.exit_code != 0 or isinstance(result.exception, KeyboardInterrupt), (
        f"Expected non-zero exit or captured KeyboardInterrupt, got exit_code={result.exit_code}"
    )
    # No success panel should appear.
    assert "Applied patch" not in result.output
    assert "Ask succeeded" not in result.output
