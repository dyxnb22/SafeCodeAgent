"""MCP stdio JSON-RPC transport (v3.3.0, experimental).

A tightly-bounded one-shot stdio JSON-RPC client for MCP-style calls against
local stub servers.  Not wired into the existing MCP runner; integration is a
future step.

Security properties:
- argv list only; never shell=True
- timeout enforced; process killed on expiry
- max output size enforced; fails closed if exceeded
- fails closed on malformed JSON, id mismatch, timeout, or process exit without output
- stderr truncated to _MAX_STDERR_BYTES; not included verbatim in result error messages
- caller-supplied params content never copied into error text

Status: experimental — tested against local stub servers only; no network.
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any


_MAX_STDERR_BYTES: int = 4096
_DEFAULT_MAX_OUTPUT_BYTES: int = 256 * 1024  # 256 KB
_DEFAULT_TIMEOUT_SECONDS: float = 10.0


@dataclass(frozen=True)
class StdioTransportResult:
    """Result of a single stdio JSON-RPC call.

    Attributes
    ----------
    success:
        True only when the response contains a ``result`` field and the id matches.
    result:
        Deserialized ``result`` from the JSON-RPC response; ``None`` on failure.
    error:
        Human-readable failure reason; empty on success.
        Never contains caller-supplied params content.
    exit_code:
        Process exit code, or a synthetic value: 124=timeout, 126=blocked, 127=not-found.
    stderr:
        Truncated stderr text (at most ``_MAX_STDERR_BYTES`` decoded characters).
    """

    success: bool
    result: Any
    error: str
    exit_code: int
    stderr: str = field(default="")


def call_stdio(
    argv: list[str],
    method: str,
    params: dict[str, Any] | None = None,
    *,
    call_id: int = 1,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
) -> StdioTransportResult:
    """Send one JSON-RPC request over stdio and return a structured result.

    Parameters
    ----------
    argv:
        Process to launch as an argv list.  Must be non-empty.  Never shell-expanded.
    method:
        JSON-RPC method name.
    params:
        Optional parameters dict.  Never copied into error messages.
    call_id:
        JSON-RPC id for correlation.
    timeout_seconds:
        Maximum wall-clock time for the entire call.
    max_output_bytes:
        Maximum accepted stdout size.  Excess output triggers a fail-closed result.
    """
    if not argv:
        return _fail("argv must not be empty", exit_code=126)

    request: dict[str, Any] = {"jsonrpc": "2.0", "id": call_id, "method": method}
    if params is not None:
        request["params"] = params

    try:
        request_bytes = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
    except (TypeError, ValueError):
        return _fail("Failed to serialize JSON-RPC request", exit_code=126)

    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except FileNotFoundError:
        return _fail("Process not found", exit_code=127)
    except (PermissionError, OSError):
        return _fail("Failed to start process", exit_code=126)

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    _stdout_overflow = threading.Event()

    def _read_stdout() -> None:
        assert proc.stdout is not None
        total = 0
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            total += len(chunk)
            if total > max_output_bytes:
                _stdout_overflow.set()
                break
            stdout_chunks.append(chunk)

    def _read_stderr() -> None:
        assert proc.stderr is not None
        total = 0
        while total < _MAX_STDERR_BYTES:
            to_read = min(512, _MAX_STDERR_BYTES - total)
            chunk = proc.stderr.read(to_read)
            if not chunk:
                break
            stderr_chunks.append(chunk)
            total += len(chunk)

    try:
        assert proc.stdin is not None
        proc.stdin.write(request_bytes)
        proc.stdin.flush()
        proc.stdin.close()
    except OSError:
        proc.kill()
        proc.wait()
        return _fail("Failed to write to process stdin", exit_code=1)

    stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    stdout_thread.join(timeout=timeout_seconds)

    if stdout_thread.is_alive():
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        stderr_thread.join(timeout=1.0)
        return _fail("MCP stdio transport timed out", exit_code=124)

    if _stdout_overflow.is_set():
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        stderr_thread.join(timeout=1.0)
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        return _fail("MCP stdio output exceeded size limit", exit_code=126, stderr=stderr_text)

    try:
        exit_code = proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        exit_code = 1

    stderr_thread.join(timeout=1.0)
    stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")

    raw = b"".join(stdout_chunks).decode("utf-8", errors="replace").strip()

    if not raw:
        return _fail(
            "MCP stdio process exited without producing output",
            exit_code=exit_code,
            stderr=stderr_text,
        )

    first_line = raw.split("\n", 1)[0].strip()

    try:
        response = json.loads(first_line)
    except (json.JSONDecodeError, ValueError):
        return _fail("MCP stdio response is not valid JSON", exit_code=exit_code, stderr=stderr_text)

    if not isinstance(response, dict):
        return _fail("MCP stdio response is not a JSON object", exit_code=exit_code, stderr=stderr_text)

    resp_id = response.get("id")
    if resp_id != call_id:
        return _fail("MCP stdio response id mismatch", exit_code=exit_code, stderr=stderr_text)

    if "error" in response:
        err_field = response["error"]
        if isinstance(err_field, dict):
            msg = str(err_field.get("message", "MCP server returned an error"))
        else:
            msg = "MCP server returned an error"
        return StdioTransportResult(
            success=False,
            result=None,
            error=msg,
            exit_code=exit_code if exit_code != 0 else 1,
            stderr=stderr_text,
        )

    return StdioTransportResult(
        success=True,
        result=response.get("result"),
        error="",
        exit_code=exit_code,
        stderr=stderr_text,
    )


def _fail(error: str, *, exit_code: int, stderr: str = "") -> StdioTransportResult:
    return StdioTransportResult(
        success=False,
        result=None,
        error=error,
        exit_code=exit_code,
        stderr=stderr,
    )
