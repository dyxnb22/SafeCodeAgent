"""Tests for v4.23.0: Anthropic native tool use + B2/B3/B16 fixes."""

from __future__ import annotations

import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.native_tools import NativeToolSpec
from safecode.agent.schemas import (
    AgentNativeToolCallResponse,
    AgentStopForUserResponse,
    RecoverableContractFailure,
)
from safecode.llm.anthropic_client import (
    AnthropicLLMClient,
    _extract_native_result,
    _extract_text,
    _native_spec_to_anthropic,
)
from safecode.llm.stream import StreamError, StreamTimeoutError


# ---------------------------------------------------------------------------
# _native_spec_to_anthropic
# ---------------------------------------------------------------------------

class TestNativeSpecToAnthropic:
    def test_converts_spec_to_anthropic_format(self):
        spec = NativeToolSpec(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        result = _native_spec_to_anthropic(spec)
        assert result["name"] == "read_file"
        assert result["description"] == "Read a file"
        assert result["input_schema"]["type"] == "object"

    def test_adds_type_object_when_missing(self):
        spec = NativeToolSpec(name="list_files", description="List", input_schema={})
        result = _native_spec_to_anthropic(spec)
        assert result["input_schema"]["type"] == "object"

    def test_preserves_existing_type(self):
        spec = NativeToolSpec(name="grep_files", description="Grep", input_schema={"type": "object"})
        result = _native_spec_to_anthropic(spec)
        assert result["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# _extract_text (B2 fix)
# ---------------------------------------------------------------------------

class TestExtractTextB2Fix:
    def test_returns_text_from_text_block(self):
        data = {"content": [{"type": "text", "text": "hello world"}]}
        assert _extract_text(data) == "hello world"

    def test_returns_empty_on_missing_content(self):
        """B2 fix: missing content returns empty string, not a crash."""
        assert _extract_text({}) == ""

    def test_returns_empty_on_none_content(self):
        """B2 fix: None content returns empty string."""
        assert _extract_text({"content": None}) == ""

    def test_returns_empty_on_empty_list(self):
        """B2 fix: empty content list returns empty string."""
        assert _extract_text({"content": []}) == ""

    def test_returns_empty_when_no_text_blocks(self):
        """B2 fix: tool_use blocks only → no text to extract."""
        data = {"content": [{"type": "tool_use", "id": "x", "name": "read_file", "input": {}}]}
        assert _extract_text(data) == ""


# ---------------------------------------------------------------------------
# _extract_native_result (B2 fix)
# ---------------------------------------------------------------------------

class TestExtractNativeResult:
    def test_returns_tool_calls_for_tool_use_blocks(self):
        data = {"content": [
            {"type": "tool_use", "id": "c1", "name": "read_file", "input": {"path": "x.py"}},
            {"type": "tool_use", "id": "c2", "name": "list_files", "input": {}},
        ]}
        result = _extract_native_result(data, step=0, method="test")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].tool_name == "read_file"
        assert result[0].input == {"path": "x.py"}
        assert result[0].call_id == "c1"
        assert result[1].tool_name == "list_files"

    def test_returns_text_for_text_only_blocks(self):
        data = {"content": [{"type": "text", "text": '{"type":"stop_for_user","reason":"done","message":"ok"}'}]}
        result = _extract_native_result(data, step=0, method="test")
        assert isinstance(result, str)
        assert "stop_for_user" in result

    def test_returns_rcf_on_missing_content(self):
        """B2 fix: missing content → RecoverableContractFailure."""
        result = _extract_native_result({}, step=0, method="test")
        assert isinstance(result, RecoverableContractFailure)
        assert "content" in result.message.lower()

    def test_returns_rcf_on_empty_content_list(self):
        """B2 fix: empty list → RecoverableContractFailure."""
        result = _extract_native_result({"content": []}, step=1, method="choose_tool_native")
        assert isinstance(result, RecoverableContractFailure)

    def test_returns_rcf_on_non_list_content(self):
        """B2 fix: non-list content → RecoverableContractFailure."""
        result = _extract_native_result({"content": "oops"}, step=0, method="test")
        assert isinstance(result, RecoverableContractFailure)

    def test_tool_use_input_defaults_to_empty_dict_on_non_dict(self):
        data = {"content": [{"type": "tool_use", "id": "c1", "name": "foo", "input": None}]}
        result = _extract_native_result(data, step=0, method="test")
        assert isinstance(result, list)
        assert result[0].input == {}

    def test_returns_rcf_when_no_tool_use_or_text(self):
        data = {"content": [{"type": "unknown_block"}]}
        result = _extract_native_result(data, step=0, method="test")
        assert isinstance(result, RecoverableContractFailure)


# ---------------------------------------------------------------------------
# StreamTimeoutError (B3 fix)
# ---------------------------------------------------------------------------

class TestStreamTimeoutError:
    def test_is_subclass_of_stream_error(self):
        """B3: StreamTimeoutError is a StreamError for consistent handling."""
        assert issubclass(StreamTimeoutError, StreamError)

    def test_can_be_raised_and_caught_as_stream_error(self):
        with pytest.raises(StreamError):
            raise StreamTimeoutError("timed out")

    def test_message_preserved(self):
        exc = StreamTimeoutError("no chunk for 30s")
        assert "30s" in str(exc)


# ---------------------------------------------------------------------------
# choose_tool_native (Anthropic provider, mocked HTTP)
# ---------------------------------------------------------------------------

def _make_anthropic_config(tmp_path):
    """Build a minimal SafeCodeConfig pointing at a mock Anthropic URL."""
    from safecode.config import SafeCodeConfig
    config = SafeCodeConfig.load(tmp_path)
    config.llm.provider = "anthropic"
    config.llm.base_url = "https://api.anthropic.com/v1/messages"
    config.llm.model = "claude-sonnet-4-6"
    config.sandbox.network_enabled = True
    return config


class TestChooseToolNativeAnthropic:
    def test_returns_tool_calls_from_tool_use_blocks(self, tmp_path):
        config = _make_anthropic_config(tmp_path)
        client = AnthropicLLMClient.__new__(AnthropicLLMClient)
        client.model = "claude-sonnet-4-6"
        client.base_url = "https://api.anthropic.com/v1/messages"
        client.api_key = "test-key"
        client._session_id = None
        client._sac_dir = None

        specs = [NativeToolSpec(name="read_file", description="Read a file")]
        fake_response = {
            "content": [
                {"type": "tool_use", "id": "tu1", "name": "read_file", "input": {"path": "foo.py"}},
            ],
            "usage": {},
        }

        with patch.object(client, "_messages_with_tools", return_value=fake_response):
            result = client.choose_tool_native("read foo.py", {}, specs, step=0)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].tool_name == "read_file"
        assert result[0].input == {"path": "foo.py"}
        assert result[0].call_id == "tu1"

    def test_returns_stop_for_user_on_text_response(self, tmp_path):
        client = AnthropicLLMClient.__new__(AnthropicLLMClient)
        client.model = "claude-sonnet-4-6"
        client.base_url = "https://api.anthropic.com/v1/messages"
        client.api_key = "test-key"
        client._session_id = None
        client._sac_dir = None

        specs = [NativeToolSpec(name="read_file", description="Read a file")]
        fake_response = {
            "content": [{"type": "text", "text": "I need more context."}],
            "usage": {},
        }

        with patch.object(client, "_messages_with_tools", return_value=fake_response):
            result = client.choose_tool_native("goal", {}, specs, step=0)

        assert isinstance(result, AgentStopForUserResponse)
        assert result.message == "I need more context."

    def test_returns_rcf_on_empty_content(self, tmp_path):
        """B2 fix: empty content in choose_tool_native → RecoverableContractFailure."""
        client = AnthropicLLMClient.__new__(AnthropicLLMClient)
        client.model = "claude-sonnet-4-6"
        client.base_url = "https://api.anthropic.com/v1/messages"
        client.api_key = "test-key"
        client._session_id = None
        client._sac_dir = None

        fake_response = {"content": [], "usage": {}}
        with patch.object(client, "_messages_with_tools", return_value=fake_response):
            result = client.choose_tool_native("goal", {}, [], step=0)

        assert isinstance(result, RecoverableContractFailure)


# ---------------------------------------------------------------------------
# _live_anthropic_ping (B16 fix)
# ---------------------------------------------------------------------------

class TestLiveAnthropicPingB16:
    def test_pass_on_200(self):
        from safecode.doctor import Doctor
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            diag = Doctor._live_anthropic_ping("test-key")

        assert diag.name == "anthropic_connectivity"
        assert diag.status.value == "PASS"

    def test_fail_on_connection_error(self):
        from safecode.doctor import Doctor
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            diag = Doctor._live_anthropic_ping("test-key")

        assert diag.status.value == "FAIL"
        assert "anthropic" in diag.name

    def test_skip_when_no_api_key(self):
        from safecode.doctor import Doctor
        diag = Doctor._live_anthropic_ping("")
        assert diag.status.value == "SKIP"
        assert "no ANTHROPIC_API_KEY" in diag.message

    def test_skip_in_offline_mode(self, monkeypatch):
        from safecode.doctor import Doctor
        monkeypatch.setenv("SAFECODE_DOCTOR_UPDATE_CHECK", "0")
        diag = Doctor._live_anthropic_ping("test-key")
        assert diag.status.value == "SKIP"
