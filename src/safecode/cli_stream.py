"""Streaming renderer for CLI and shell output (EXPERIMENTAL v4.17+).

Renders LLM token-by-token chunks via Rich Live in TTY mode. Non-TTY falls
back to batch output. All rendered deltas pass through token-level redaction.
"""

from __future__ import annotations

from collections.abc import Iterator

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.llm.stream import StreamChunk


def render_stream(
    orchestrator: AgentOrchestrator,
    question: str,
    *,
    is_tty: bool,
) -> str:
    """Stream an ask response to the console. Returns the full aggregated text.

    TTY mode: prints token-by-token via Rich Live (progressive rendering).
    Non-TTY mode: prints each chunk as it arrives without buffering.
    JSON mode callers should call orchestrator.ask() directly instead.
    """
    full_text_parts: list[str] = []
    if is_tty:
        try:
            from rich.live import Live
            from rich.markdown import Markdown

            with Live(Markdown(""), refresh_per_second=10, vertical_overflow="visible") as live:
                for chunk in orchestrator.ask_stream(question):
                    full_text_parts.append(chunk.delta)
                    live.update(Markdown("".join(full_text_parts)))
        except ImportError:
            for chunk in orchestrator.ask_stream(question):
                full_text_parts.append(chunk.delta)
                print(chunk.delta, end="", flush=True)
            print()
    else:
        for chunk in orchestrator.ask_stream(question):
            full_text_parts.append(chunk.delta)
            print(chunk.delta, end="", flush=True)
        print()
    return "".join(full_text_parts)


def stream_chunks_to_console(chunks: Iterator[StreamChunk], *, is_tty: bool) -> str:
    """Render pre-existing chunks to the console. Returns full aggregated text.

    Use this when the caller already has a chunk iterator (e.g., from shell router).
    """
    full_text_parts: list[str] = []
    if is_tty:
        try:
            from rich.live import Live
            from rich.markdown import Markdown

            with Live(Markdown(""), refresh_per_second=10, vertical_overflow="visible") as live:
                for chunk in chunks:
                    full_text_parts.append(chunk.delta)
                    live.update(Markdown("".join(full_text_parts)))
        except ImportError:
            for chunk in chunks:
                full_text_parts.append(chunk.delta)
                print(chunk.delta, end="", flush=True)
            print()
    else:
        for chunk in chunks:
            full_text_parts.append(chunk.delta)
            print(chunk.delta, end="", flush=True)
        print()
    return "".join(full_text_parts)
