"""web_fetch native tool — HTTP GET for text/HTML content (v4.24.0+, EXPERIMENTAL).

Safety invariants:
- Only http/https URLs accepted; others blocked.
- Requires network_enabled=True in config; blocked by default.
- Content-Type must start with text/; binary responses rejected.
- HTML <script> and <style> blocks stripped before output.
- Output capped at max_bytes (default 50 000).
- At most 3 redirects honored; more → blocked.
- URL never appears in error messages (follows B12 sanitization pattern).
- redact_secrets() applied to output before returning.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets

_DEFAULT_MAX_BYTES = 50_000
_MAX_REDIRECTS = 3
_CONNECT_TIMEOUT = 15  # seconds


class _MaxRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Limit HTTP redirects to _MAX_REDIRECTS."""

    def __init__(self) -> None:
        self._count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        self._count += 1
        if self._count > _MAX_REDIRECTS:
            raise urllib.error.HTTPError(
                req.full_url, 310, f"Too many redirects (max {_MAX_REDIRECTS})", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _strip_html(html: str) -> str:
    """Strip <script>, <style> blocks and all remaining tags; collapse whitespace."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _fetch_url(url: str, max_bytes: int) -> NativeToolResult:
    """Perform the HTTP GET; returns NativeToolResult. Never raises."""
    # Validate URL scheme before any network call.
    if not url.lower().startswith(("http://", "https://")):
        return NativeToolResult(
            call_id="", tool_name="web_fetch", status="blocked",
            error="Only http:// and https:// URLs are supported.",
        )

    redirect_handler = _MaxRedirectHandler()
    opener = urllib.request.build_opener(redirect_handler)
    req = urllib.request.Request(url, headers={"User-Agent": "SafeCode-WebFetch/1.0"})

    try:
        with opener.open(req, timeout=_CONNECT_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if not content_type.lower().startswith("text/"):
                return NativeToolResult(
                    call_id="", tool_name="web_fetch", status="blocked",
                    error=f"Unsupported content type: {content_type!r}. Only text/* responses accepted.",
                )
            raw = resp.read(max_bytes)
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].strip().split(";")[0].strip()
            text = raw.decode(charset, errors="replace")
            if "html" in content_type.lower():
                text = _strip_html(text)
            text = redact_secrets(text)
            return NativeToolResult(
                call_id="", tool_name="web_fetch", status="success",
                output=text,
                metadata={"bytes_read": len(raw), "content_type": content_type},
            )
    except urllib.error.HTTPError as exc:
        return NativeToolResult(
            call_id="", tool_name="web_fetch", status="error",
            error=f"HTTP error {exc.code} fetching URL.",
        )
    except urllib.error.URLError as exc:
        return NativeToolResult(
            call_id="", tool_name="web_fetch", status="error",
            error=f"Network error: {type(exc.reason).__name__}",
        )
    except Exception as exc:
        return NativeToolResult(
            call_id="", tool_name="web_fetch", status="error",
            error=f"Fetch failed: {type(exc).__name__}",
        )


def _web_fetch_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    url: str = inp.get("url", "").strip()
    max_bytes: int = int(inp.get("max_bytes", _DEFAULT_MAX_BYTES))

    if not url:
        return NativeToolResult(
            call_id=call_id, tool_name="web_fetch", status="error",
            error="Missing 'url' input.",
        )

    # Network policy gate — blocked by default.
    config = SafeCodeConfig.load(project_root)
    if not getattr(config.sandbox, "network_enabled", False):
        return NativeToolResult(
            call_id=call_id, tool_name="web_fetch", status="blocked",
            error="web_fetch requires network: true in config (disabled by default).",
        )

    result = _fetch_url(url, max_bytes)
    return NativeToolResult(
        call_id=call_id,
        tool_name="web_fetch",
        status=result.status,
        output=result.output,
        error=result.error,
        metadata=result.metadata,
    )


WEB_FETCH_SPEC = NativeToolSpec(
    name="web_fetch",
    description=(
        "Fetch a web page via HTTP GET. Returns stripped text content. "
        "Requires network: true. Blocked by default."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "http:// or https:// URL to fetch."},
            "max_bytes": {
                "type": "integer",
                "description": f"Maximum bytes to read (default {_DEFAULT_MAX_BYTES}).",
            },
        },
        "required": ["url"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
)


def register_web_fetch_tool(dispatcher: NativeToolDispatcher, project_root: Path) -> None:
    """Register web_fetch on a dispatcher, injecting project_root."""

    def _handler(call_id: str, inp: dict) -> NativeToolResult:
        return _web_fetch_handler(call_id, {"_project_root": str(project_root), **inp})

    dispatcher.register(WEB_FETCH_SPEC, _handler)
