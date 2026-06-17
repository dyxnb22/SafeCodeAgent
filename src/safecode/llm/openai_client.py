"""Minimal OpenAI-compatible LLM client.

The client only returns text. Patch text is still parsed and validated by the
SafeCode runtime before any file write can happen.

v4.23.1: native tool use via OpenAI function calling; B1/B12 fixes.
"""

import json
import os
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
    parse_agent_contract_response,
    validate_provider_json,
)
from safecode.agent.prompts import SYSTEM_PROMPT

if TYPE_CHECKING:
    from safecode.agent.native_tools import NativeToolSpec
from safecode.config import SafeCodeConfig
from safecode.llm.cost import SessionCostAccumulator, TokenUsage
from safecode.llm.retry import retry_call
from safecode.llm.stream import StreamChunk, StreamError, aggregate_chunks, parse_sse_stream
from safecode.sandbox.network import NetworkPolicy


def _log_retry(attempt: int, reason: str) -> None:
    warnings.warn(f"LLM retry attempt {attempt}: {reason}", RuntimeWarning, stacklevel=4)


def _native_spec_to_openai(spec: "NativeToolSpec") -> dict[str, Any]:
    """Convert a NativeToolSpec to the OpenAI function calling tools format (v4.23.1)."""
    schema = dict(spec.input_schema)
    if "type" not in schema:
        schema["type"] = "object"
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": schema,
        },
    }


_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


def _normalize_endpoint(base_url: str) -> str:
    """Join /v1/chat/completions onto a raw base URL defensively.

    Rules:
    - If base_url already ends with /v1/chat/completions (or /v1/chat/completions/),
      return as-is (no double-append).
    - If base_url ends with /v1 or /v1/, append /chat/completions.
    - Otherwise, strip trailing slash and append /v1/chat/completions.
    """
    url = base_url.rstrip("/")
    if url.endswith("/v1/chat/completions"):
        return base_url.rstrip("/")
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + _CHAT_COMPLETIONS_PATH


def _extract_patch_envelope(text: str) -> str:
    """Return the SafeCode patch envelope from provider output when present."""
    start = text.find("*** Begin Patch")
    end_marker = "*** End Patch"
    end = text.find(end_marker, start if start >= 0 else 0)
    if start >= 0 and end >= 0:
        return text[start : end + len(end_marker)].strip()
    return text.strip()


class OpenAICompatibleLLMClient:
    """Call an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        config: SafeCodeConfig,
        *,
        session_id: str | None = None,
        sac_dir: Path | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        progress_callback: "Callable[[str], None] | None" = None,
    ) -> None:
        # Network policy is asserted against the raw base_url (before normalization).
        NetworkPolicy(config).assert_allowed(config.llm.base_url)
        self.model = config.llm.model
        # Normalize: join /v1/chat/completions onto the base URL.
        self.base_url = _normalize_endpoint(config.llm.base_url)
        # Resolve API key: provider env var -> OPENAI_API_KEY -> SAFECODE_LLM_API_KEY -> user config.
        self.api_key = (
            os.getenv(api_key_env)
            or (os.getenv("OPENAI_API_KEY") if api_key_env != "OPENAI_API_KEY" else None)
            or os.getenv("SAFECODE_LLM_API_KEY")
            or config.llm.api_key
        )
        if not self.api_key:
            env_hint = api_key_env if api_key_env != "OPENAI_API_KEY" else "OPENAI_API_KEY"
            raise RuntimeError(
                f"{env_hint} or SAFECODE_LLM_API_KEY is required for real LLM mode."
            )
        self._session_id = session_id
        self._sac_dir = sac_dir
        # Reliability config (v4.10.3)
        self._request_timeout = getattr(config.llm, "request_timeout_seconds", 60)
        self._max_retries = getattr(config.llm, "max_retries", 3)
        self._retry_base_delay = getattr(config.llm, "retry_base_delay_seconds", 0.5)
        self._progress_callback = progress_callback
        # Accumulates token usage from the most recent _chat call; read by propose_patch.
        self._last_token_usage: dict[str, int] = {"input": 0, "output": 0}

    def ask(self, question: str, context: dict) -> AgentAnswer:
        """Answer a read-only question."""
        content = self._chat(
            [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nAnswer read-only project questions."},
                {"role": "user", "content": f"Question: {question}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        return AgentAnswer(content=content)

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        """Return a structured plan for a user goal."""
        response = self._chat_agent_json(
            [
                {"role": "system", "content": self._contract_prompt("plan")},
                {"role": "user", "content": f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}"},
            ],
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
        """Return the next structured tool intent, user stop, or a recoverable failure.

        ``RecoverableContractFailure`` is returned (not raised) so the agent loop
        can journal the event and retry exactly once without crashing.
        """
        response = self._chat_agent_json(
            [
                {"role": "system", "content": self._contract_prompt("tool_intent or stop_for_user")},
                {"role": "user", "content": f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}"},
            ],
            step=step,
            method="choose_tool",
        )
        if isinstance(response, RecoverableContractFailure):
            return response
        if not isinstance(response, (AgentToolIntentResponse, AgentStopForUserResponse)):
            raise ValueError(f"Expected tool_intent or stop_for_user response, got {response.type}.")
        return response

    _PATCH_SYSTEM_PROMPT = (
        "{system}\nReturn exactly one JSON object and no prose. "
        'The JSON shape must be {{"type":"patch","patch_text":"...","explanation":"..."}}. '
        "The patch_text value must be a SafeCode SEARCH/REPLACE patch. "
        "If the task touches multiple files, include ALL changed files in one patch "
        "using multiple *** Update File: sections inside a single *** Begin Patch / *** End Patch envelope. "
        "Exact format:\n"
        "*** Begin Patch\n"
        "*** Update File: path/to/first.py\n"
        "SEARCH:\n"
        "old text exactly as it appears in the file\n"
        "REPLACE:\n"
        "new text\n"
        "*** Update File: path/to/second.py\n"
        "SEARCH:\n"
        "old text exactly as it appears in that file\n"
        "REPLACE:\n"
        "new text\n"
        "*** End Patch\n"
        "Do not use unified diff hunks, @@ markers, Markdown fences, or prose inside patch_text. "
        "SEARCH must not be empty."
    )

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        """Return patch text, leaving parsing and validation to SafeCode.

        Retries once when the first response contains no patch envelope — this
        catches models that respond with planning prose instead of a direct patch.
        """
        system = self._PATCH_SYSTEM_PROMPT.format(system=SYSTEM_PROMPT)
        user_msg = f"Task: {task}\nContext: {json.dumps(context)[:12000]}"

        self._last_token_usage = {"input": 0, "output": 0}  # reset before this request

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
        content = self._chat(messages)
        patch_text = self._resolve_patch_text(content)

        if "*** Begin Patch" not in patch_text:
            # Model returned prose / planning text instead of a patch; retry once
            # with an explicit "output the patch now" instruction.
            retry_messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "You responded with planning text instead of a patch. "
                        "The file contents are already in the context above. "
                        "Output the patch NOW using *** Begin Patch ... *** End Patch. "
                        "No explanation."
                    ),
                },
            ]
            content = self._chat(retry_messages)
            patch_text = self._resolve_patch_text(content)

        return AgentPatchResponse(
            patch_text=patch_text,
            explanation="OpenAI-compatible patch response.",
            input_tokens=self._last_token_usage["input"],
            output_tokens=self._last_token_usage["output"],
        )

    def _resolve_patch_text(self, content: str) -> str:
        """Extract the patch envelope from a raw LLM response (JSON or plain text)."""
        parsed = validate_provider_json(content, method="propose_patch")
        if isinstance(parsed, AgentPatchResponse):
            return _extract_patch_envelope(parsed.patch_text)
        return _extract_patch_envelope(content)

    def choose_tool_native(
        self,
        goal: str,
        context: dict,
        tool_specs: list["NativeToolSpec"],
        *,
        step: int = 0,
        conversation_history: "list[dict] | None" = None,
    ) -> list[AgentNativeToolCallResponse] | AgentStopForUserResponse | RecoverableContractFailure:
        """Call with OpenAI function calling; return tool calls or stop (v4.23.1, EXPERIMENTAL).

        Sends ``tool_specs`` as the OpenAI ``tools`` parameter. When the model
        responds with ``tool_calls``, maps them to ``AgentNativeToolCallResponse``.

        ``conversation_history`` (v6.7.0): optional prior messages from ConversationBuffer.
        When provided they are inserted between the system message and the current
        user turn so the model has full conversational context.
        """
        tools = [_native_spec_to_openai(spec) for spec in tool_specs]
        current_user_msg = {"role": "user", "content": f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}"}
        history = list(conversation_history) if conversation_history else []
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [current_user_msg]
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": 0,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        _last_http_error: list[urllib.error.HTTPError] = []

        def _do_request() -> dict:
            _last_http_error.clear()
            try:
                with urllib.request.urlopen(request, timeout=self._request_timeout) as response:
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
            data = retry_call(
                _do_request,
                max_attempts=self._max_retries,
                base_delay=self._retry_base_delay,
                log_fn=_log_retry,
                get_retry_after=_get_retry_after,
            )
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        self._record_usage(data)

        # B1 fix: bounds check before accessing choices
        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            return RecoverableContractFailure(
                step=step,
                method="choose_tool_native",
                message="Provider returned empty choices array",
            )
        message = choices[0].get("message") or {} if isinstance(choices[0], dict) else {}
        tool_calls_raw = message.get("tool_calls") or []
        if tool_calls_raw:
            calls = []
            for tc in tool_calls_raw:
                if not isinstance(tc, dict) or "function" not in tc:
                    continue
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {}
                calls.append(AgentNativeToolCallResponse(
                    tool_name=fn.get("name", ""),
                    input=args if isinstance(args, dict) else {},
                    call_id=tc.get("id", ""),
                ))
            if calls:
                return calls
        # No tool calls: parse content as stop or wrap
        content = message.get("content") or ""
        if content:
            parsed = validate_provider_json(content, step=step, method="choose_tool_native")
            if isinstance(parsed, AgentStopForUserResponse):
                return parsed
            return AgentStopForUserResponse(reason="done", message=content, requires_approval=False)
        return RecoverableContractFailure(
            step=step,
            method="choose_tool_native",
            message="Empty response from provider",
        )

    def _chat_agent_json(
        self,
        messages: list[dict[str, str]],
        *,
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
        raw = self._chat(messages)
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

    def _chat(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        _last_http_error: list[urllib.error.HTTPError] = []

        def _do_request() -> dict:
            _last_http_error.clear()
            try:
                with urllib.request.urlopen(request, timeout=self._request_timeout) as response:
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
            data = retry_call(
                _do_request,
                max_attempts=self._max_retries,
                base_delay=self._retry_base_delay,
                log_fn=_log_retry,
                get_retry_after=_get_retry_after,
                progress_callback=self._progress_callback,
            )
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        self._record_usage(data)
        # B1 fix: bounds check before indexing choices[]; return empty string
        # on empty/missing choices so callers get RecoverableContractFailure
        # from validate_provider_json rather than a raw IndexError/KeyError.
        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            return ""
        message = choices[0].get("message") or {} if isinstance(choices[0], dict) else {}
        return message.get("content") or ""

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        _lines_fn: Callable[[list[dict[str, str]]], Iterator[str]] | None = None,
    ) -> Iterator[StreamChunk]:
        """Stream a chat response as SSE chunks.

        ``_lines_fn`` is injectable for tests: given messages, return an
        iterator of raw SSE lines. When omitted, a real HTTPS request is made.

        Fails closed on malformed events and connection errors — partial output
        is discarded, session state is not mutated.
        """
        if _lines_fn is not None:
            lines = _lines_fn(messages)
        else:
            lines = self._http_stream_lines(messages)
        try:
            yield from parse_sse_stream(lines)
        except ValueError as exc:
            raise StreamError(f"Malformed stream event: {exc}") from exc

    def _http_stream_lines(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Open an SSE stream and yield raw text lines."""
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "stream": True,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                for raw_line in response:
                    yield raw_line.decode("utf-8").rstrip("\n\r")
        except urllib.error.URLError as exc:
            raise StreamError(f"LLM stream request failed: {exc}") from exc

    def _record_usage(self, data: dict) -> None:
        usage_raw = data.get("usage") or {}
        if not usage_raw:
            return
        prompt = int(usage_raw.get("prompt_tokens", 0))
        completion = int(usage_raw.get("completion_tokens", 0))
        # Update last-call cache so propose_patch can embed token counts in the response.
        self._last_token_usage["input"] += prompt
        self._last_token_usage["output"] += completion
        if self._session_id is None or self._sac_dir is None:
            return
        usage = TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=int(usage_raw.get("total_tokens", prompt + completion)),
            cost_usd=None,
        )
        try:
            SessionCostAccumulator(self._sac_dir, self._session_id).record(usage)
        except Exception:
            pass
