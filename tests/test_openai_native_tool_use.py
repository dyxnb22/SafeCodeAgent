"""Tests for v4.23.1: OpenAI native tool use + B1/B12 fixes."""

from __future__ import annotations

import json
import warnings
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.native_tools import NativeToolSpec
from safecode.agent.schemas import (
    AgentNativeToolCallResponse,
    AgentStopForUserResponse,
    RecoverableContractFailure,
)
from safecode.llm.openai_client import (
    OpenAICompatibleLLMClient,
    _native_spec_to_openai,
)
from safecode.llm.retry import _sanitize_retry_reason


# ---------------------------------------------------------------------------
# _native_spec_to_openai
# ---------------------------------------------------------------------------

class TestNativeSpecToOpenAI:
    def test_converts_to_function_format(self):
        spec = NativeToolSpec(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        result = _native_spec_to_openai(spec)
        assert result["type"] == "function"
        assert result["function"]["name"] == "read_file"
        assert result["function"]["description"] == "Read a file"
        assert result["function"]["parameters"]["type"] == "object"

    def test_adds_type_object_when_missing(self):
        spec = NativeToolSpec(name="list_files", description="List files", input_schema={})
        result = _native_spec_to_openai(spec)
        assert result["function"]["parameters"]["type"] == "object"

    def test_preserves_existing_schema(self):
        schema = {"type": "object", "required": ["path"]}
        spec = NativeToolSpec(name="grep_files", description="Grep", input_schema=schema)
        result = _native_spec_to_openai(spec)
        assert result["function"]["parameters"]["required"] == ["path"]


# ---------------------------------------------------------------------------
# B1 fix: empty choices[] bounds check
# ---------------------------------------------------------------------------

def _make_openai_client(tmp_path):
    """Build a minimal OpenAICompatibleLLMClient for testing."""
    from safecode.config import SafeCodeConfig
    config = SafeCodeConfig.load(tmp_path)
    config.llm.provider = "openai"
    config.llm.base_url = "https://api.openai.com"
    config.llm.model = "gpt-4o"
    config.sandbox.network_enabled = True
    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client.model = "gpt-4o"
    client.base_url = "https://api.openai.com/v1/chat/completions"
    client.api_key = "test-key"
    client._session_id = None
    client._sac_dir = None
    client._request_timeout = 60
    client._max_retries = 3
    client._retry_base_delay = 0.5
    client._progress_callback = None
    return client


class TestB1EmptyChoicesBoundsCheck:
    def test_chat_returns_empty_string_on_missing_choices(self, tmp_path):
        """B1 fix: _chat() returns '' when choices is missing."""
        client = _make_openai_client(tmp_path)
        fake_data = {"usage": {}}  # no choices key

        with patch.object(client, "_chat", wraps=client._chat):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(fake_data).encode()
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp
                result = client._chat([{"role": "user", "content": "hi"}])

        assert result == ""

    def test_chat_returns_empty_string_on_empty_choices(self, tmp_path):
        """B1 fix: _chat() returns '' when choices is empty list."""
        client = _make_openai_client(tmp_path)
        fake_data = {"choices": [], "usage": {}}

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(fake_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = client._chat([{"role": "user", "content": "hi"}])

        assert result == ""

    def test_choose_tool_native_rcf_on_empty_choices(self, tmp_path):
        """B1 fix: choose_tool_native returns RCF when choices is empty."""
        client = _make_openai_client(tmp_path)
        fake_data = {"choices": [], "usage": {}}

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(fake_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            specs = [NativeToolSpec(name="read_file", description="Read")]
            result = client.choose_tool_native("goal", {}, specs, step=0)

        assert isinstance(result, RecoverableContractFailure)
        assert "empty choices" in result.message.lower()


# ---------------------------------------------------------------------------
# choose_tool_native OpenAI
# ---------------------------------------------------------------------------

class TestChooseToolNativeOpenAI:
    def test_returns_tool_calls_from_tool_calls_field(self, tmp_path):
        client = _make_openai_client(tmp_path)
        fake_data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"foo.py"}'},
                        }
                    ],
                }
            }],
            "usage": {},
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(fake_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            specs = [NativeToolSpec(name="read_file", description="Read")]
            result = client.choose_tool_native("read foo.py", {}, specs)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].tool_name == "read_file"
        assert result[0].input == {"path": "foo.py"}
        assert result[0].call_id == "call_1"

    def test_returns_stop_for_user_on_text_content(self, tmp_path):
        client = _make_openai_client(tmp_path)
        fake_data = {
            "choices": [{
                "message": {"content": "I need more info.", "tool_calls": None}
            }],
            "usage": {},
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(fake_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = client.choose_tool_native("goal", {}, [])

        assert isinstance(result, AgentStopForUserResponse)
        assert result.message == "I need more info."

    def test_handles_invalid_json_arguments_gracefully(self, tmp_path):
        client = _make_openai_client(tmp_path)
        fake_data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "search_files", "arguments": "NOT JSON"},
                        }
                    ],
                }
            }],
            "usage": {},
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(fake_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = client.choose_tool_native("goal", {}, [])

        assert isinstance(result, list)
        assert result[0].input == {}


# ---------------------------------------------------------------------------
# B12 fix: URL sanitization in retry logs
# ---------------------------------------------------------------------------

class TestB12RetrySanitization:
    def test_url_replaced_with_placeholder(self):
        """B12 fix: URLs in retry reasons are replaced with [URL]."""
        result = _sanitize_retry_reason("Connection error: https://api.openai.com/v1/chat/completions")
        assert "[URL]" in result
        assert "openai.com" not in result

    def test_multiple_urls_sanitized(self):
        reason = "Failed to connect to https://api.openai.com and https://backup.api.com"
        result = _sanitize_retry_reason(reason)
        assert result.count("[URL]") == 2
        assert "openai.com" not in result

    def test_no_url_unchanged(self):
        reason = "HTTP 429 rate limit"
        result = _sanitize_retry_reason(reason)
        assert result == "HTTP 429 rate limit"

    def test_http_url_also_sanitized(self):
        reason = "http://internal-proxy:8080/v1 connection refused"
        result = _sanitize_retry_reason(reason)
        assert "[URL]" in result
        assert "internal-proxy" not in result

    def test_log_fn_receives_sanitized_reason(self, tmp_path):
        """B12 fix: retry_call log_fn sees sanitized reason, not raw URL."""
        import urllib.error
        from safecode.llm.retry import retry_call

        logged: list[str] = []

        def fake_log(attempt: int, reason: str) -> None:
            logged.append(reason)

        # Simulate a URLError with a URL in the message
        call_count = 0

        def failing_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                err = urllib.error.URLError("https://api.openai.com/v1 unreachable")
                raise err
            return "ok"

        result = retry_call(failing_fn, max_attempts=3, base_delay=0, log_fn=fake_log)
        assert result == "ok"
        # Logged reasons should not contain raw URLs
        for msg in logged:
            assert "openai.com" not in msg
