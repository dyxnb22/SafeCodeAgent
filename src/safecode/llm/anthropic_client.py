"""Anthropic API LLM client.

Implements the same high-level contract as OpenAICompatibleLLMClient,
reusing retry, cost, and streaming infrastructure.

v4.23.0: native tool use via Anthropic `tools` parameter; B2/B3/B16 fixes.
Provider behavior is experimental — not promoted to a public stable contract.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

from safecode.agent.schemas import (
    AgentAnswer,
    AgentError,
    AgentNativeToolCallResponse,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
    validate_provider_json,
)
from safecode.agent.prompts import SYSTEM_PROMPT
from safecode.config import SafeCodeConfig
from safecode.llm.cost import SessionCostAccumulator, TokenUsage
from safecode.llm.retry import retry_call
from safecode.llm.stream import StreamChunk, StreamError, StreamTimeoutError, parse_sse_stream
from safecode.sandbox.network import NetworkPolicy

if TYPE_CHECKING:
    from safecode.agent.native_tools import NativeToolSpec

_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096
_STREAM_CHUNK_TIMEOUT = 30  # seconds; B3 fix


def _log_retry(attempt: int, reason: str) -> None:
    warnings.warn(f"Anthropic LLM retry attempt {attempt}: {reason}", RuntimeWarning, stacklevel=4)


def _native_spec_to_anthropic(spec: "NativeToolSpec") -> dict[str, Any]:
    """Convert a NativeToolSpec to the Anthropic tools parameter format."""
    schema = dict(spec.input_schema)
    if "type" not in schema:
        schema["type"] = "object"
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": schema,
    }


def _extract_text(data: dict) -> str:
    """Extract text from Anthropic Messages API response.

    B2 fix: validate content blocks exist before indexing; return empty string
    rather than crashing when the response has no text blocks.
    """
    content = data.get("content")
    # B2: validate non-empty list before access
    if not content or not isinstance(content, list):
        return ""
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts)


def _extract_native_result(
    data: dict,
    *,
    step: int,
    method: str,
) -> list[AgentNativeToolCallResponse] | str | RecoverableContractFailure:
    """Extract tool_use or text blocks from Anthropic response.

    Returns:
      - list[AgentNativeToolCallResponse] when tool_use blocks are present
      - str (text content) when only text blocks are present
      - RecoverableContractFailure when content is missing or malformed (B2 fix)
    """
    content = data.get("content")
    # B2 fix: fail gracefully on empty/missing content
    if not content or not isinstance(content, list):
        return RecoverableContractFailure(
            step=step,
            method=method,
            message="Empty or missing content blocks in Anthropic response",
        )

    tool_calls: list[AgentNativeToolCallResponse] = []
    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use":
            raw_input = block.get("input")
            tool_calls.append(AgentNativeToolCallResponse(
                tool_name=block.get("name", ""),
                input=raw_input if isinstance(raw_input, dict) else {},
                call_id=block.get("id", ""),
            ))
        elif block_type == "text":
            text_parts.append(block.get("text", ""))

    if tool_calls:
        return tool_calls
    text = "".join(text_parts).strip()
    if text:
        return text
    return RecoverableContractFailure(
        step=step,
        method=method,
        message="No tool_use or text blocks in Anthropic response",
    )


class AnthropicLLMClient:
    """Call the Anthropic Messages API.

    Implements the same four-method contract as ``OpenAICompatibleLLMClient``
    so it is a drop-in provider alternative for the orchestrator and agent loop.

    v4.23.0 additions: native tool use via ``choose_tool_native()``.

    The default base URL is ``https://api.anthropic.com/v1/messages``.
    Override via ``config.llm.base_url`` for testing or proxy use.
    """

    def __init__(
        self,
        config: SafeCodeConfig,
        *,
        session_id: str | None = None,
        sac_dir: Path | None = None,
    ) -> None:
        NetworkPolicy(config).assert_allowed(config.llm.base_url)
        self.model = config.llm.model or "claude-sonnet-4-6"
        self.base_url = config.llm.base_url
        self.api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("SAFECODE_LLM_API_KEY") or config.llm.api_key
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY or SAFECODE_LLM_API_KEY is required for Anthropic provider.")
        self._session_id = session_id
        self._sac_dir = sac_dir

    # ------------------------------------------------------------------
    # Public LLMClient interface
    # ------------------------------------------------------------------

    def ask(self, question: str, context: dict) -> AgentAnswer:
        """Answer a read-only question."""
        content = self._messages(
            system=f"{SYSTEM_PROMPT}\nAnswer read-only project questions.",
            user=f"Question: {question}\nContext: {json.dumps(context)[:12000]}",
        )
        return AgentAnswer(content=content)

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        """Return a structured plan for a user goal."""
        response = self._messages_agent_json(
            system=self._contract_prompt("plan"),
            user=f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}",
            method="plan",
        )
        if isinstance(response, RecoverableContractFailure):
            raise ValueError(f"Provider plan response failed validation: {response.message}")
        if not isinstance(response, AgentPlanResponse):
            raise ValueError(f"Expected plan response, got {response.type}.")
        return response

    def choose_tool(
        self, goal: str, context: dict, *, step: int = 0
    ) -> AgentToolIntentResponse | AgentStopForUserResponse | RecoverableContractFailure:
        """Return the next structured tool intent, user stop, or a recoverable failure."""
        response = self._messages_agent_json(
            system=self._contract_prompt("tool_intent or stop_for_user"),
            user=f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}",
            step=step,
            method="choose_tool",
        )
        if isinstance(response, RecoverableContractFailure):
            return response
        if not isinstance(response, (AgentToolIntentResponse, AgentStopForUserResponse)):
            raise ValueError(f"Expected tool_intent or stop_for_user response, got {response.type}.")
        return response

    def choose_tool_native(
        self,
        goal: str,
        context: dict,
        tool_specs: list["NativeToolSpec"],
        *,
        step: int = 0,
    ) -> list[AgentNativeToolCallResponse] | AgentStopForUserResponse | RecoverableContractFailure:
        """Call Anthropic with native tool use; return tool calls or stop (v4.23.0, EXPERIMENTAL).

        Sends ``tool_specs`` as the Anthropic ``tools`` parameter. When the model
        responds with ``tool_use`` blocks, maps them to ``AgentNativeToolCallResponse``.
        When the model responds with text, parses it as a stop_for_user fallback.
        """
        tools = [_native_spec_to_anthropic(spec) for spec in tool_specs]
        data = self._messages_with_tools(
            system=SYSTEM_PROMPT,
            user=f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}",
            tools=tools,
        )
        result = _extract_native_result(data, step=step, method="choose_tool_native")
        if isinstance(result, RecoverableContractFailure):
            return result
        if isinstance(result, list):
            return result
        # Text fallback: try to parse as stop_for_user; on non-JSON, wrap as one
        parsed = validate_provider_json(result, step=step, method="choose_tool_native")
        if isinstance(parsed, AgentStopForUserResponse):
            return parsed
        # Non-JSON text or unrecognized type → wrap as stop_for_user so the loop
        # can surface it to the user rather than silently dropping it.
        return AgentStopForUserResponse(reason="done", message=result, requires_approval=False)

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        """Return patch text, leaving parsing and validation to SafeCode."""
        content = self._messages(
            system=(
                f"{SYSTEM_PROMPT}\nReturn only a SafeCode patch proposal using *** Begin Patch, "
                "*** Update File, SEARCH, REPLACE, and *** End Patch. Do not explain."
            ),
            user=f"Task: {task}\nContext: {json.dumps(context)[:12000]}",
        )
        return AgentPatchResponse(patch_text=content, explanation="Anthropic patch response.")

    # ------------------------------------------------------------------
    # Streaming (SupportsStreaming)
    # ------------------------------------------------------------------

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        _lines_fn: Callable[[list[dict[str, str]]], Iterator[str]] | None = None,
    ) -> Iterator[StreamChunk]:
        """Stream a chat response via Anthropic SSE.

        ``_lines_fn`` is injectable for tests (returns raw SSE lines given messages).
        Fails closed on malformed events and connection errors.
        """
        if _lines_fn is not None:
            lines = _lines_fn(messages)
        else:
            lines = self._http_stream_lines_anthropic(messages)
        try:
            yield from _parse_anthropic_sse(lines)
        except ValueError as exc:
            raise StreamError(f"Malformed Anthropic stream event: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _messages_agent_json(
        self,
        *,
        system: str,
        user: str,
        step: int = 0,
        method: str = "choose_tool",
    ) -> (
        AgentAnswer
        | AgentPlanResponse
        | AgentToolIntentResponse
        | AgentPatchResponse
        | AgentStopForUserResponse
        | AgentError
        | RecoverableContractFailure
    ):
        raw = self._messages(system=system, user=user)
        return validate_provider_json(raw, step=step, method=method)

    def _contract_prompt(self, expected_type: str) -> str:
        return (
            f"{SYSTEM_PROMPT}\nReturn exactly one JSON object and no prose. "
            f"The response type must be {expected_type}. Supported response shapes: "
            '{"type":"answer","content":"..."}, '
            '{"type":"plan","goal":"...","steps":["..."]}, '
            '{"type":"tool_intent","intent":{"type":"read","target":"...","description":"..."},"rationale":"..."}, '
            '{"type":"patch","patch_text":"*** Begin Patch\\n...\\n*** End Patch","explanation":"..."}, '
            '{"type":"stop_for_user","reason":"...","message":"...","requires_approval":true}.'
        )

    def _messages(self, *, system: str, user: str) -> str:
        """Call the Anthropic Messages API and return the assistant's text."""
        payload = json.dumps({
            "model": self.model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": user, "cache_control": {"type": "ephemeral"}}
            ]}],
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        _last_http_error: list[urllib.error.HTTPError] = []

        def _do_request() -> dict:
            _last_http_error.clear()
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                _last_http_error.append(exc)
                raise

        def _get_retry_after() -> float | None:
            if _last_http_error:
                from safecode.llm.retry import _parse_retry_after
                header = _last_http_error[-1].headers.get("Retry-After", "")
                return _parse_retry_after(header) if header else None
            return None

        try:
            data = retry_call(_do_request, log_fn=_log_retry, get_retry_after=_get_retry_after)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Anthropic request failed: {exc}") from exc

        self._record_usage(data)
        return _extract_text(data)

    def _messages_with_tools(self, *, system: str, user: str, tools: list[dict]) -> dict:
        """Call Anthropic Messages API with native tool definitions; return raw response dict."""
        payload = json.dumps({
            "model": self.model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": tools,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": user, "cache_control": {"type": "ephemeral"}}
            ]}],
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        _last_http_error: list[urllib.error.HTTPError] = []

        def _do_request() -> dict:
            _last_http_error.clear()
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                _last_http_error.append(exc)
                raise

        def _get_retry_after() -> float | None:
            if _last_http_error:
                from safecode.llm.retry import _parse_retry_after
                header = _last_http_error[-1].headers.get("Retry-After", "")
                return _parse_retry_after(header) if header else None
            return None

        try:
            data = retry_call(_do_request, log_fn=_log_retry, get_retry_after=_get_retry_after)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Anthropic request failed: {exc}") from exc
        self._record_usage(data)
        return data

    def _record_usage(self, data: dict) -> None:
        if self._session_id is None or self._sac_dir is None:
            return
        usage_raw = data.get("usage") or {}
        if not usage_raw:
            return
        prompt = int(usage_raw.get("input_tokens", 0))
        completion = int(usage_raw.get("output_tokens", 0))
        cache_read = int(usage_raw.get("cache_read_input_tokens", 0))
        cache_creation = int(usage_raw.get("cache_creation_input_tokens", 0))
        usage = TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            cost_usd=None,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )
        try:
            SessionCostAccumulator(self._sac_dir, self._session_id).record(usage)
        except Exception:
            pass

    def _http_stream_lines_anthropic(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Open an Anthropic SSE stream and yield raw text lines.

        B3 fix: per-chunk timeout of 30 seconds. If no data arrives within
        30s, raises StreamTimeoutError (recoverable in the agent loop).
        """
        user_content = " ".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        ) or "assist"
        payload = json.dumps({
            "model": self.model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "messages": [{"role": "user", "content": user_content}],
            "stream": True,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            # B3: timeout=30 applies per socket read (per chunk), not just connection
            with urllib.request.urlopen(request, timeout=_STREAM_CHUNK_TIMEOUT) as response:
                for raw_line in response:
                    yield raw_line.decode("utf-8").rstrip("\n\r")
        except socket.timeout as exc:
            raise StreamTimeoutError(
                f"Anthropic stream timed out: no chunk received within {_STREAM_CHUNK_TIMEOUT}s"
            ) from exc
        except urllib.error.URLError as exc:
            raise StreamError(f"Anthropic stream request failed: {exc}") from exc


def _parse_anthropic_sse(lines: Iterator[str]) -> Iterator[StreamChunk]:
    """Parse Anthropic SSE stream lines into StreamChunks.

    Anthropic streaming events use:
      event: content_block_delta
      data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}

    The ``message_stop`` event signals end of stream.
    """
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[len("data:"):].strip()
        if payload in ("[DONE]", ""):
            continue
        # Raises ValueError on malformed JSON — propagated by stream_chat as StreamError.
        data = json.loads(payload)
        event_type = data.get("type", "")
        if event_type == "content_block_delta":
            delta_obj = data.get("delta") or {}
            if isinstance(delta_obj, dict) and delta_obj.get("type") == "text_delta":
                text = delta_obj.get("text") or ""
                yield StreamChunk(delta=str(text))
        elif event_type == "message_delta":
            stop_reason = (data.get("delta") or {}).get("stop_reason")
            if stop_reason:
                yield StreamChunk(delta="", finish_reason=stop_reason)
        elif event_type == "message_stop":
            yield StreamChunk(delta="", finish_reason="stop")
