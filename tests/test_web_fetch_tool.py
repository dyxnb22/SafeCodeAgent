"""Tests for v4.24.0: web_fetch native tool."""

from __future__ import annotations

import io
import urllib.error
from http.client import HTTPMessage
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.native_tools import NativeToolSpec
from safecode.agent.web_fetch_tool import (
    WEB_FETCH_SPEC,
    _strip_html,
    _web_fetch_handler,
    register_web_fetch_tool,
)


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------

class TestStripHtml:
    def test_removes_script_blocks(self):
        html = "<html><script>alert(1)</script><p>Hello</p></html>"
        result = _strip_html(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_style_blocks(self):
        html = "<html><style>body{color:red}</style><p>World</p></html>"
        result = _strip_html(html)
        assert "color" not in result
        assert "World" in result

    def test_strips_remaining_tags(self):
        html = "<div><p>Keep this text</p></div>"
        result = _strip_html(html)
        assert "<" not in result
        assert "Keep this text" in result

    def test_collapses_whitespace(self):
        html = "<p>A</p>   <p>B</p>"
        result = _strip_html(html)
        assert "  " not in result


# ---------------------------------------------------------------------------
# WEB_FETCH_SPEC
# ---------------------------------------------------------------------------

class TestWebFetchSpec:
    def test_is_native_tool_spec(self):
        assert isinstance(WEB_FETCH_SPEC, NativeToolSpec)

    def test_name_and_schema(self):
        assert WEB_FETCH_SPEC.name == "web_fetch"
        assert "url" in WEB_FETCH_SPEC.input_schema.get("properties", {})

    def test_not_requires_approval(self):
        assert WEB_FETCH_SPEC.requires_approval is False


# ---------------------------------------------------------------------------
# _web_fetch_handler: network disabled (default)
# ---------------------------------------------------------------------------

class TestWebFetchBlockedByDefault:
    def test_blocked_when_network_disabled(self, tmp_path):
        """web_fetch is blocked by default (network_enabled=False)."""
        result = _web_fetch_handler("c1", {"_project_root": str(tmp_path), "url": "https://example.com"})
        assert result.status == "blocked"
        assert "network" in result.error.lower()

    def test_error_on_missing_url(self, tmp_path):
        result = _web_fetch_handler("c1", {"_project_root": str(tmp_path)})
        assert result.status == "error"
        assert "url" in result.error.lower()

    def test_blocked_on_non_http_scheme(self, tmp_path):
        """Only http/https URLs allowed."""
        with patch("safecode.agent.web_fetch_tool.SafeCodeConfig") as MockConfig:
            mock_cfg = MagicMock()
            mock_cfg.sandbox.network_enabled = True
            MockConfig.load.return_value = mock_cfg
            result = _web_fetch_handler("c1", {
                "_project_root": str(tmp_path),
                "url": "file:///etc/passwd",
            })
        assert result.status == "blocked"


# ---------------------------------------------------------------------------
# _web_fetch_handler: successful fetch (mocked network)
# ---------------------------------------------------------------------------

def _make_mock_response(body: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200):
    """Build a fake urllib response object."""
    mock_headers = MagicMock()
    mock_headers.get.return_value = content_type
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.headers = mock_headers
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestWebFetchSuccess:
    def _handler_with_network(self, tmp_path, url, body, content_type="text/html; charset=utf-8"):
        with patch("safecode.agent.web_fetch_tool.SafeCodeConfig") as MockConfig:
            mock_cfg = MagicMock()
            mock_cfg.sandbox.network_enabled = True
            MockConfig.load.return_value = mock_cfg
            mock_resp = _make_mock_response(body, content_type)
            with patch("safecode.agent.web_fetch_tool.urllib.request.build_opener") as mock_opener_fn:
                opener = MagicMock()
                opener.open.return_value.__enter__ = lambda s: mock_resp
                opener.open.return_value.__exit__ = MagicMock(return_value=False)
                # Make opener.open() return the mock_resp as a context manager
                ctx = MagicMock()
                ctx.__enter__ = lambda s: mock_resp
                ctx.__exit__ = MagicMock(return_value=False)
                opener.open.return_value = ctx
                mock_opener_fn.return_value = opener
                return _web_fetch_handler("c1", {"_project_root": str(tmp_path), "url": url})

    def test_returns_stripped_html(self, tmp_path):
        body = b"<html><script>bad()</script><p>Good content</p></html>"
        result = self._handler_with_network(tmp_path, "https://example.com", body)
        assert result.status == "success"
        assert "Good content" in result.output
        assert "bad()" not in result.output

    def test_returns_text_plain_as_is(self, tmp_path):
        body = b"Plain text content here"
        result = self._handler_with_network(tmp_path, "https://example.com", body, "text/plain; charset=utf-8")
        assert result.status == "success"
        assert "Plain text content" in result.output

    def _handler_blocked_or_error(self, tmp_path, url, *, side_effect=None, body=b"", content_type="application/octet-stream"):
        """Helper for tests that expect blocked/error without actual content."""
        with patch("safecode.agent.web_fetch_tool.SafeCodeConfig") as MockConfig:
            mock_cfg = MagicMock()
            mock_cfg.sandbox.network_enabled = True
            MockConfig.load.return_value = mock_cfg
            with patch("safecode.agent.web_fetch_tool.urllib.request.build_opener") as mock_opener_fn:
                opener = MagicMock()
                if side_effect:
                    opener.open.side_effect = side_effect
                else:
                    mock_resp = _make_mock_response(body, content_type)
                    ctx = MagicMock()
                    ctx.__enter__ = lambda s: mock_resp
                    ctx.__exit__ = MagicMock(return_value=False)
                    opener.open.return_value = ctx
                mock_opener_fn.return_value = opener
                return _web_fetch_handler("c1", {"_project_root": str(tmp_path), "url": url})

    def test_blocked_on_binary_content_type(self, tmp_path):
        result = self._handler_blocked_or_error(
            tmp_path, "https://example.com/file.bin",
            body=b"\x00\x01\x02", content_type="application/octet-stream"
        )
        assert result.status == "blocked"

    def test_http_error_returns_error_result(self, tmp_path):
        result = self._handler_blocked_or_error(
            tmp_path, "https://example.com/missing",
            side_effect=urllib.error.HTTPError("https://example.com", 404, "Not Found", {}, None)
        )
        assert result.status == "error"
        assert "404" in result.error
        # URL must NOT appear in error messages (B12 pattern)
        assert "example.com" not in result.error

    def test_url_not_in_network_error_message(self, tmp_path):
        """B12 pattern: URL must not appear in error messages."""
        result = self._handler_blocked_or_error(
            tmp_path, "https://secret-internal.example.com",
            side_effect=urllib.error.URLError("Connection refused")
        )
        assert "secret-internal" not in (result.error or "")


# ---------------------------------------------------------------------------
# register_web_fetch_tool
# ---------------------------------------------------------------------------

class TestRegisterWebFetchTool:
    def test_registration_adds_web_fetch(self, tmp_path):
        from safecode.agent.native_dispatcher import NativeToolDispatcher
        dispatcher = NativeToolDispatcher()
        register_web_fetch_tool(dispatcher, tmp_path)
        assert any(s.name == "web_fetch" for s in dispatcher.specs())
