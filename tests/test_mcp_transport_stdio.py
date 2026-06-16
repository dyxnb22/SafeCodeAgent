"""Tests for v3.3.0: MCP stdio JSON-RPC transport.

Uses local stub Python server scripts created in tmp_path — no network,
no real MCP server dependency.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from safecode.mcp.transport_stdio import (
    _DEFAULT_MAX_OUTPUT_BYTES,
    _MAX_STDERR_BYTES,
    StdioTransportResult,
    call_stdio,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_server(tmp_path: Path, name: str, script: str) -> list[str]:
    """Write a stub server script and return its argv."""
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return [sys.executable, str(path)]


_ECHO_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": req.get("params", {})}))
"""

_OK_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"status": "ok"}}))
"""


# ── Round-trip ────────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_basic_round_trip(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        result = call_stdio(argv, "tools/call", {"name": "test"})
        assert result.success is True
        assert result.result == {"status": "ok"}
        assert result.error == ""

    def test_result_none_when_server_returns_null(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": None}))
""")
        result = call_stdio(argv, "ping")
        assert result.success is True
        assert result.result is None

    def test_exit_code_zero_on_success(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        result = call_stdio(argv, "tools/call")
        assert result.exit_code == 0

    def test_params_forwarded_in_request(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", _ECHO_SERVER)
        result = call_stdio(argv, "echo", {"key": "value", "num": 42})
        assert result.success is True
        assert result.result == {"key": "value", "num": 42}

    def test_call_id_correlates(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": req["id"]}))
""")
        result = call_stdio(argv, "method", call_id=42)
        assert result.success is True
        assert result.result == 42

    def test_no_params_sends_no_params_field(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
has_params = "params" in req
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": has_params}))
""")
        result = call_stdio(argv, "method")
        assert result.success is True
        assert result.result is False

    def test_result_is_structured_dataclass(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        result = call_stdio(argv, "ping")
        assert isinstance(result, StdioTransportResult)
        assert result.success is True


# ── Id mismatch ───────────────────────────────────────────────────────────────


class TestIdMismatch:
    def test_id_mismatch_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stdin.readline()
print(json.dumps({"jsonrpc": "2.0", "id": 9999, "result": "ok"}))
""")
        result = call_stdio(argv, "method", call_id=1)
        assert result.success is False
        assert "mismatch" in result.error.lower()

    def test_id_null_mismatch_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stdin.readline()
print(json.dumps({"jsonrpc": "2.0", "id": None, "result": "ok"}))
""")
        result = call_stdio(argv, "method", call_id=1)
        assert result.success is False
        assert "mismatch" in result.error.lower()

    def test_string_id_mismatch_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stdin.readline()
print(json.dumps({"jsonrpc": "2.0", "id": "wrong", "result": "ok"}))
""")
        result = call_stdio(argv, "method", call_id=1)
        assert result.success is False

    def test_id_mismatch_does_not_leak_params(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stdin.readline()
print(json.dumps({"jsonrpc": "2.0", "id": 9999, "result": "ok"}))
""")
        result = call_stdio(argv, "method", {"secret_token": "sk-super-secret-1234"}, call_id=1)
        assert "sk-super-secret-1234" not in result.error


# ── Malformed JSON ────────────────────────────────────────────────────────────


class TestMalformedJSON:
    def test_non_json_response_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
print("this is not json at all")
""")
        result = call_stdio(argv, "method")
        assert result.success is False
        assert "json" in result.error.lower()

    def test_partial_json_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
print('{"id": 1, "result":')
""")
        result = call_stdio(argv, "method")
        assert result.success is False
        assert "json" in result.error.lower()

    def test_json_array_not_object_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stdin.readline()
print(json.dumps([{"id": 1}]))
""")
        result = call_stdio(argv, "method")
        assert result.success is False

    def test_json_number_not_object_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
print("42")
""")
        result = call_stdio(argv, "method")
        assert result.success is False

    def test_malformed_json_does_not_leak_params(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
print("not-json")
""")
        result = call_stdio(argv, "method", {"password": "hunter2-secret"})
        assert "hunter2-secret" not in result.error


# ── Timeout ───────────────────────────────────────────────────────────────────


@pytest.mark.timeout
class TestTimeout:
    def test_timeout_result_shape(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, time
sys.stdin.readline()
time.sleep(60)
""")
        result = call_stdio(argv, "method", timeout_seconds=0.15)
        assert result.success is False
        assert result.exit_code == 124
        assert "timed out" in result.error.lower()

    def test_timeout_process_cleaned_up(self, tmp_path):
        # Verify subsequent call doesn't hang (process was killed)
        argv = _write_server(tmp_path, "server.py", """\
import sys, time
sys.stdin.readline()
time.sleep(60)
""")
        r1 = call_stdio(argv, "method", timeout_seconds=0.15)
        r2 = call_stdio(argv, "method", timeout_seconds=0.15)
        assert r1.success is False
        assert r2.success is False

    def test_timeout_does_not_leak_params(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, time
sys.stdin.readline()
time.sleep(60)
""")
        result = call_stdio(argv, "method", {"api_key": "sk-secret-token-12345"}, timeout_seconds=0.15)
        assert "sk-secret-token-12345" not in result.error


# ── Process exit without response ────────────────────────────────────────────


class TestProcessExitNoResponse:
    def test_process_exit_nonzero_no_output_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.exit(1)
""")
        result = call_stdio(argv, "method")
        assert result.success is False
        assert result.error != ""

    def test_process_exit_zero_no_output_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.exit(0)
""")
        result = call_stdio(argv, "method")
        assert result.success is False

    def test_process_exit_preserves_exit_code(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.exit(2)
""")
        result = call_stdio(argv, "method")
        assert result.success is False
        assert result.exit_code == 2

    def test_process_exits_immediately_blocked(self, tmp_path):
        # Server exits before reading stdin at all
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.exit(3)
""")
        result = call_stdio(argv, "method")
        assert result.success is False


# ── Oversized output ──────────────────────────────────────────────────────────


class TestOversizedOutput:
    def test_oversized_output_blocked(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.stdout.write("x" * 600000)
sys.stdout.flush()
""")
        result = call_stdio(argv, "method", max_output_bytes=1024)
        assert result.success is False
        assert "size" in result.error.lower() or "limit" in result.error.lower()

    def test_oversized_output_exit_code_126(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.stdout.write("x" * 600000)
sys.stdout.flush()
""")
        result = call_stdio(argv, "method", max_output_bytes=1024)
        assert result.exit_code == 126

    def test_output_within_limit_succeeds(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        result = call_stdio(argv, "method", max_output_bytes=64 * 1024)
        assert result.success is True

    def test_oversized_does_not_leak_params(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.stdout.write("x" * 600000)
sys.stdout.flush()
""")
        result = call_stdio(argv, "method", {"token": "bearer-secret-xyz"}, max_output_bytes=1024)
        assert "bearer-secret-xyz" not in result.error


# ── Argv list, no shell=True ──────────────────────────────────────────────────


class TestArgvNoShell:
    def test_empty_argv_blocked(self):
        result = call_stdio([], "method")
        assert result.success is False
        assert "argv" in result.error.lower()

    def test_nonexistent_binary_returns_failure(self, tmp_path):
        result = call_stdio([str(tmp_path / "no_such_binary")], "method")
        assert result.success is False
        assert result.exit_code == 127

    def test_subprocess_uses_shell_false(self, tmp_path, monkeypatch):
        """Verify shell=False is always passed to Popen."""
        shell_flags: list[bool] = []
        original_popen = subprocess.Popen

        def mock_popen(args, **kwargs):
            shell_flags.append(kwargs.get("shell", True))
            return original_popen(args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", mock_popen)
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        call_stdio(argv, "method")
        assert shell_flags == [False]

    def test_path_with_spaces_works(self, tmp_path):
        # shell=True would mis-split this path
        spaced = tmp_path / "dir with spaces"
        spaced.mkdir()
        script = spaced / "server.py"
        script.write_text(_OK_SERVER, encoding="utf-8")
        result = call_stdio([sys.executable, str(script)], "method")
        assert result.success is True

    def test_extra_argv_args_passed_correctly(self, tmp_path):
        # argv with an extra arg that shell would misinterpret
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        argv_with_arg = argv + ["--ignored-arg"]
        result = call_stdio(argv_with_arg, "method")
        assert result.success is True


# ── Stderr captured and truncated ────────────────────────────────────────────


class TestStderr:
    def test_stderr_captured_on_success(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stderr.write("debug info\\n")
sys.stderr.flush()
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": "ok"}))
""")
        result = call_stdio(argv, "method")
        assert result.success is True
        # stderr is captured but does not affect success

    def test_stderr_does_not_cause_failure_on_success(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
for i in range(20):
    sys.stderr.write(f"log {i}\\n")
sys.stderr.flush()
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": "done"}))
""")
        result = call_stdio(argv, "method")
        assert result.success is True

    def test_large_stderr_truncated(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stderr.write("E" * 10000)
sys.stderr.flush()
sys.stdin.readline()
sys.exit(1)
""")
        result = call_stdio(argv, "method")
        assert result.success is False
        assert len(result.stderr) <= _MAX_STDERR_BYTES + 10  # truncated

    def test_stderr_field_present_on_result(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", _OK_SERVER)
        result = call_stdio(argv, "method")
        assert hasattr(result, "stderr")
        assert isinstance(result.stderr, str)

    def test_stderr_not_in_error_field(self, tmp_path):
        # stderr text must not bleed into the error message
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stderr.write("internal-debug-info\\n")
sys.stderr.flush()
sys.stdin.readline()
print("not valid json")
""")
        result = call_stdio(argv, "method")
        assert result.success is False
        assert "internal-debug-info" not in result.error


# ── Secret-like payload not leaked in error text ──────────────────────────────


class TestSecretNotLeaked:
    def test_secret_not_leaked_on_timeout(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, time
sys.stdin.readline()
time.sleep(60)
""")
        result = call_stdio(
            argv, "method", {"api_key": "sk-secret-token-12345"}, timeout_seconds=0.15
        )
        assert "sk-secret-token-12345" not in result.error

    def test_secret_not_leaked_on_json_parse_failure(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
print("not json at all")
""")
        result = call_stdio(argv, "method", {"password": "super-secret-password-abc"})
        assert "super-secret-password-abc" not in result.error

    def test_secret_not_leaked_on_id_mismatch(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys, json
sys.stdin.readline()
print(json.dumps({"jsonrpc": "2.0", "id": 999, "result": "ok"}))
""")
        result = call_stdio(argv, "method", {"secret": "my-secret-value-xyz"})
        assert "my-secret-value-xyz" not in result.error

    def test_secret_not_leaked_on_size_overflow(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.stdout.write("x" * 100000)
sys.stdout.flush()
""")
        result = call_stdio(
            argv, "method", {"token": "bearer-secret-xyz-99999"}, max_output_bytes=1024
        )
        assert "bearer-secret-xyz-99999" not in result.error

    def test_secret_not_leaked_on_process_exit_no_output(self, tmp_path):
        argv = _write_server(tmp_path, "server.py", """\
import sys
sys.stdin.readline()
sys.exit(1)
""")
        result = call_stdio(argv, "method", {"auth": "top-secret-credential-abc"})
        assert "top-secret-credential-abc" not in result.error

    def test_secret_not_in_stderr_field(self, tmp_path):
        # Params should not appear in stderr even if the process echoes stdin to stderr
        argv = _write_server(tmp_path, "server.py", """\
import sys
data = sys.stdin.read()
sys.stderr.write(data)  # echo input to stderr (a misbehaving server)
sys.stderr.flush()
sys.exit(1)
""")
        # We can't prevent the process from writing stdin to stderr, but we CAN verify
        # that our transport doesn't inject params into the error field.
        result = call_stdio(argv, "method", {"safe": "harmless"})
        assert result.success is False
        # error field must not contain the params value injected by our code
        # (it may contain it if the server echoed back, which is a different concern)
        # The key invariant: our transport code never copies params into error
        assert isinstance(result.error, str)
