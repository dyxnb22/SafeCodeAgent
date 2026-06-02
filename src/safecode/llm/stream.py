"""Streaming abstraction for LLM provider responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass(frozen=True)
class StreamChunk:
    """A single streamed text delta from an LLM provider."""

    delta: str
    finish_reason: str | None = None


@dataclass(frozen=True)
class StreamResult:
    """Aggregated result from a completed stream."""

    text: str
    finish_reason: str | None = None


class StreamError(RuntimeError):
    """Raised when a stream fails in a non-recoverable way."""


def aggregate_chunks(chunks: Iterator[StreamChunk]) -> StreamResult:
    """Collect all chunks into a StreamResult. Exhausts the iterator."""
    parts: list[str] = []
    finish_reason: str | None = None
    for chunk in chunks:
        parts.append(chunk.delta)
        if chunk.finish_reason is not None:
            finish_reason = chunk.finish_reason
    return StreamResult(text="".join(parts), finish_reason=finish_reason)


def parse_sse_line(line: str) -> StreamChunk | None:
    """Parse one SSE data line into a StreamChunk.

    Returns None for the [DONE] sentinel, blank lines, and comment lines.
    Raises ValueError if the data payload is not valid JSON.
    """
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return None
    payload = stripped[len("data:"):].strip()
    if payload == "[DONE]":
        return None
    # Raises ValueError on malformed JSON — caller decides how to handle.
    data = json.loads(payload)
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return StreamChunk(delta="")
    choice = choices[0]
    if not isinstance(choice, dict):
        return StreamChunk(delta="")
    delta_obj = choice.get("delta") or {}
    text = delta_obj.get("content") or "" if isinstance(delta_obj, dict) else ""
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    return StreamChunk(delta=str(text), finish_reason=finish_reason or None)


def parse_sse_stream(lines: Iterator[str]) -> Iterator[StreamChunk]:
    """Parse an SSE line stream into StreamChunks.

    Skips non-data lines and [DONE]. Re-raises ValueError for malformed JSON
    so callers can decide whether to fail closed or treat as recoverable.
    """
    for line in lines:
        chunk = parse_sse_line(line)
        if chunk is not None:
            yield chunk


class SupportsStreaming(Protocol):
    """Optional streaming capability that LLM providers may implement.

    Providers that implement this alongside ``LLMClient`` expose chunk-level
    output. The default non-streaming path is always available as a fallback.
    """

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[StreamChunk]:
        """Stream a chat response as chunks.

        Must fail closed if the stream is cancelled or errors before finishing.
        Must not corrupt session state on early termination.
        """
        ...
