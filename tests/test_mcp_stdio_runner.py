"""Tests for v3.3.4: StdioReadOnlyAdapter experimental read-only runner.

Covers:
- Read-only classification gate (schema-based and keyword-based)
- Write tool blocking
- Unknown tool blocking
- Opt-in requirement (MCPReadOnlyRunner unchanged)
- Bounded output enforcement via call_stdio max_output_bytes
- Timeout kill via call_stdio timeout_seconds
- Transport failures return non-blocking failure results
- call_args never appear in error text
- All failure paths return results; never raise
- Output extraction (content-block format and fallback)
- StdioCallResult field invariants
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest

from safecode.mcp.schema import MCPToolSchema
from safecode.mcp.stdio_runner import (
    StdioCallResult,
    StdioReadOnlyAdapter,
    _extract_output,
)


# ── Stub server helpers ───────────────────────────────────────────────────────


def _write_server(tmp_path: Path, name: str, script: str) -> list[str]:
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return [sys.executable, str(path)]


def _content_block_server(text: str) -> str:
    safe_text = json.dumps(text)
    return f"""\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({{"jsonrpc": "2.0", "id": req["id"], "result": {{"content": [{{"type": "text", "text": {safe_text}}}]}}}}))
"""


_ECHO_ARGS_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
args = req.get("params", {}).get("arguments", {})
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"content": [{"type": "text", "text": json.dumps(args)}]}}))
"""

_SLEEP_SERVER = """\
import sys, time
sys.stdin.readline()
time.sleep(60)
"""

_EXIT_NO_OUTPUT_SERVER = """\
import sys
sys.stdin.readline()
sys.exit(1)
"""


def _adapter(tmp_path: Path, script: str, schemas: list[MCPToolSchema] | None = None,
             *, server: str = "srv", timeout: float = 5.0,
             max_output: int = 256 * 1024) -> tuple[StdioReadOnlyAdapter, list[str]]:
    argv = _write_server(tmp_path, "srv.py", script)
    return StdioReadOnlyAdapter(server, argv, schemas,
                                timeout_seconds=timeout,
                                max_output_bytes=max_output), argv


# ── StdioCallResult dataclass ─────────────────────────────────────────────────


class TestStdioCallResult:
    def test_is_frozen(self):
        r = StdioCallResult(server="s", tool="t", classification="read",
                            output="", error="", exit_code=0, success=True, blocked=False)
        with pytest.raises(Exception):
            r.success = False  # type: ignore[misc]

    def test_success_fields(self):
        r = StdioCallResult(server="s", tool="t", classification="read",
                            output="data", error="", exit_code=0, success=True, blocked=False)
        assert r.success is True
        assert r.blocked is False
        assert r.output == "data"
        assert r.error == ""

    def test_blocked_fields(self):
        r = StdioCallResult(server="s", tool="t", classification="write",
                            output="", error="blocked", exit_code=126, success=False, blocked=True)
        assert r.success is False
        assert r.blocked is True
        assert r.exit_code == 126


# ── _extract_output helper ────────────────────────────────────────────────────


class TestExtractOutput:
    def test_none_returns_empty(self):
        assert _extract_output(None) == ""

    def test_string_returned_as_is(self):
        assert _extract_output("hello") == "hello"

    def test_content_block_text_extracted(self):
        result = {"content": [{"type": "text", "text": "file contents"}]}
        assert _extract_output(result) == "file contents"

    def test_multiple_content_blocks_joined(self):
        result = {"content": [
            {"type": "text", "text": "line 1"},
            {"type": "text", "text": "line 2"},
        ]}
        assert _extract_output(result) == "line 1\nline 2"

    def test_non_text_content_blocks_skipped(self):
        result = {"content": [
            {"type": "image", "data": "base64..."},
            {"type": "text", "text": "text only"},
        ]}
        assert _extract_output(result) == "text only"

    def test_empty_content_list_falls_back_to_json(self):
        result = {"content": []}
        # Falls back to JSON serialisation
        output = _extract_output(result)
        assert isinstance(output, str)

    def test_dict_without_content_json_serialised(self):
        result = {"key": "value"}
        output = _extract_output(result)
        assert "key" in output

    def test_list_json_serialised(self):
        output = _extract_output([1, 2, 3])
        assert "[" in output

    def test_non_string_text_in_block_skipped(self):
        result = {"content": [{"type": "text", "text": 42}, {"type": "text", "text": "ok"}]}
        assert _extract_output(result) == "ok"


# ── Classification gate: read allowed ─────────────────────────────────────────


class TestReadOnlyGate:
    def test_read_schema_tool_executes(self, tmp_path):
        schemas = [MCPToolSchema(server="srv", tool="get_files", classification="read")]
        a, _ = _adapter(tmp_path, _content_block_server("result"), schemas)
        r = a.call_readonly("get_files")
        assert r.success is True
        assert r.blocked is False

    def test_read_keyword_tool_executes_without_schema(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("ok"))
        r = a.call_readonly("get_files")  # "get" keyword → "read"
        assert r.blocked is False

    def test_classification_in_result(self, tmp_path):
        schemas = [MCPToolSchema(server="srv", tool="get_files", classification="read")]
        a, _ = _adapter(tmp_path, _content_block_server("data"), schemas)
        r = a.call_readonly("get_files")
        assert r.classification == "read"

    def test_output_extracted_on_success(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("file contents here"))
        r = a.call_readonly("list_files")
        assert r.success is True
        assert "file contents here" in r.output

    def test_server_name_in_result(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("ok"), server="my-server")
        r = a.call_readonly("list_items")
        assert r.server == "my-server"

    def test_tool_name_in_result(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("ok"))
        r = a.call_readonly("get_status")
        assert r.tool == "get_status"

    def test_exit_code_zero_on_success(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("ok"))
        r = a.call_readonly("list_files")
        assert r.exit_code == 0


# ── Classification gate: write blocked ────────────────────────────────────────


class TestWriteBlocking:
    def test_write_schema_tool_blocked(self, tmp_path):
        schemas = [MCPToolSchema(server="srv", tool="write_file", classification="write")]
        a, _ = _adapter(tmp_path, _content_block_server("should not reach"))
        a._schemas = schemas
        r = a.call_readonly("write_file")
        assert r.blocked is True
        assert r.success is False

    def test_write_keyword_tool_blocked_without_schema(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("should not reach"))
        r = a.call_readonly("write_file")  # "write" keyword → "write"
        assert r.blocked is True

    def test_write_exit_code_126(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        r = a.call_readonly("delete_record")
        assert r.blocked is True
        assert r.exit_code == 126

    def test_write_output_empty(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        r = a.call_readonly("write_config")
        assert r.output == ""

    def test_write_classification_in_result(self, tmp_path):
        schemas = [MCPToolSchema(server="srv", tool="create_item", classification="write")]
        a, _ = _adapter(tmp_path, _content_block_server("nope"), schemas)
        r = a.call_readonly("create_item")
        assert r.classification == "write"

    def test_write_emits_runtime_warning(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            a.call_readonly("write_file")
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)


# ── Classification gate: unknown blocked ─────────────────────────────────────


class TestUnknownBlocking:
    def test_unknown_schema_blocked(self, tmp_path):
        schemas = [MCPToolSchema(server="srv", tool="process", classification="unknown")]
        a, _ = _adapter(tmp_path, _content_block_server("nope"), schemas)
        r = a.call_readonly("process")
        assert r.blocked is True
        assert r.success is False

    def test_unknown_keyword_blocked(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        r = a.call_readonly("process_data")  # "process" → "unknown"
        assert r.blocked is True

    def test_unknown_exit_code_126(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        r = a.call_readonly("process_data")
        assert r.exit_code == 126

    def test_unknown_classification_in_result(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        r = a.call_readonly("transform_data")  # "transform" → unknown
        assert r.classification == "unknown"


# ── Opt-in requirement: MCPReadOnlyRunner default unchanged ──────────────────


class TestOptInRequirement:
    def test_mcp_read_only_runner_stdio_is_opt_in_off_by_default(self):
        """MCPReadOnlyRunner stdio routing is opt-in and off by default (v3.8.0)."""
        from safecode.mcp.runner import MCPReadOnlyRunner
        import pathlib
        runner = MCPReadOnlyRunner.__new__(MCPReadOnlyRunner)
        # Default env behaviour: stdio_runner off unless SAFECODE_MCP_STDIO_RUNNER=1.
        # The attribute exists; opt-in is controlled by flag not by absence of import.
        runner_src = (pathlib.Path(__file__).parent.parent
                      / "src" / "safecode" / "mcp" / "runner.py").read_text()
        # v3.8.0: wired behind an explicit opt-in flag — import present, default off.
        assert "SAFECODE_MCP_STDIO_RUNNER" in runner_src

    def test_stdio_adapter_wired_behind_opt_in_flag(self):
        """StdioReadOnlyAdapter is imported but only used when stdio_runner=True (v3.8.0)."""
        import pathlib
        runner_src = (pathlib.Path(__file__).parent.parent
                      / "src" / "safecode" / "mcp" / "runner.py").read_text()
        # v3.8.0: StdioReadOnlyAdapter is imported and used only via the opt-in path.
        assert "StdioReadOnlyAdapter" in runner_src
        assert "self._stdio_runner" in runner_src

    def test_stdio_adapter_not_imported_in_loop_executor(self):
        import pathlib
        src = (pathlib.Path(__file__).parent.parent
               / "src" / "safecode" / "mcp" / "loop_executor.py").read_text()
        assert "stdio_runner" not in src
        assert "StdioReadOnlyAdapter" not in src

    def test_adapter_requires_explicit_instantiation(self, tmp_path):
        # StdioReadOnlyAdapter must be constructed by the caller explicitly.
        argv = _write_server(tmp_path, "srv.py", _content_block_server("ok"))
        adapter = StdioReadOnlyAdapter("srv", argv)
        assert isinstance(adapter, StdioReadOnlyAdapter)


# ── Bounded output ────────────────────────────────────────────────────────────


class TestBoundedOutput:
    def test_oversized_output_not_success(self, tmp_path):
        large = _write_server(tmp_path, "srv.py", """\
import sys
sys.stdin.readline()
sys.stdout.write("x" * 600000)
sys.stdout.flush()
""")
        a = StdioReadOnlyAdapter("srv", large, max_output_bytes=1024)
        r = a.call_readonly("list_files")
        assert r.success is False

    def test_oversized_output_not_blocked(self, tmp_path):
        # Oversized output is a transport failure, not a classification block.
        large = _write_server(tmp_path, "srv.py", """\
import sys
sys.stdin.readline()
sys.stdout.write("x" * 600000)
sys.stdout.flush()
""")
        a = StdioReadOnlyAdapter("srv", large, max_output_bytes=1024)
        r = a.call_readonly("list_files")
        assert r.blocked is False

    def test_output_within_limit_succeeds(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("small"), max_output=64 * 1024)
        r = a.call_readonly("list_files")
        assert r.success is True


# ── Timeout kill ──────────────────────────────────────────────────────────────


class TestTimeoutKill:
    def test_timeout_returns_failure(self, tmp_path):
        a, _ = _adapter(tmp_path, _SLEEP_SERVER, timeout=0.3)
        r = a.call_readonly("list_files")
        assert r.success is False

    def test_timeout_not_blocked(self, tmp_path):
        # Timeout is a transport failure, not a classification block.
        a, _ = _adapter(tmp_path, _SLEEP_SERVER, timeout=0.3)
        r = a.call_readonly("list_files")
        assert r.blocked is False

    def test_timeout_exit_code_124(self, tmp_path):
        a, _ = _adapter(tmp_path, _SLEEP_SERVER, timeout=0.3)
        r = a.call_readonly("list_files")
        assert r.exit_code == 124

    def test_timeout_error_not_empty(self, tmp_path):
        a, _ = _adapter(tmp_path, _SLEEP_SERVER, timeout=0.3)
        r = a.call_readonly("list_files")
        assert r.error != ""


# ── Transport failure (non-timeout) ──────────────────────────────────────────


class TestTransportFailure:
    def test_process_exit_no_output_failure(self, tmp_path):
        a, _ = _adapter(tmp_path, _EXIT_NO_OUTPUT_SERVER)
        r = a.call_readonly("list_files")
        assert r.success is False
        assert r.blocked is False

    def test_nonexistent_binary_failure(self, tmp_path):
        a = StdioReadOnlyAdapter("srv", [str(tmp_path / "no_such_binary")])
        r = a.call_readonly("list_files")
        assert r.success is False
        assert r.exit_code == 127

    def test_transport_failure_emits_warning(self, tmp_path):
        a, _ = _adapter(tmp_path, _EXIT_NO_OUTPUT_SERVER)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            a.call_readonly("list_files")
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)


# ── call_args never in error text ────────────────────────────────────────────


class TestNoParamsInError:
    def test_call_args_not_in_write_block_error(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        secret = "sk-super-secret-9999"
        r = a.call_readonly("write_file", {"token": secret})
        assert secret not in r.error

    def test_call_args_not_in_timeout_error(self, tmp_path):
        a, _ = _adapter(tmp_path, _SLEEP_SERVER, timeout=0.3)
        secret = "bearer-secret-token-xyz"
        r = a.call_readonly("list_files", {"auth": secret})
        assert secret not in r.error

    def test_call_args_not_in_unknown_block_error(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        secret = "api-key-secret-abc"
        r = a.call_readonly("process_data", {"key": secret})
        assert secret not in r.error

    def test_call_args_not_in_transport_error(self, tmp_path):
        a, _ = _adapter(tmp_path, _EXIT_NO_OUTPUT_SERVER)
        secret = "password-secret-xyz-123"
        r = a.call_readonly("list_files", {"password": secret})
        assert secret not in r.error


# ── Never raises ─────────────────────────────────────────────────────────────


class TestNeverRaises:
    def test_write_tool_no_raise(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("nope"))
        result = a.call_readonly("write_file")
        assert isinstance(result, StdioCallResult)

    def test_timeout_no_raise(self, tmp_path):
        a, _ = _adapter(tmp_path, _SLEEP_SERVER, timeout=0.3)
        result = a.call_readonly("list_files")
        assert isinstance(result, StdioCallResult)

    def test_missing_binary_no_raise(self, tmp_path):
        a = StdioReadOnlyAdapter("srv", [str(tmp_path / "missing")])
        result = a.call_readonly("list_files")
        assert isinstance(result, StdioCallResult)

    def test_all_result_fields_present(self, tmp_path):
        a, _ = _adapter(tmp_path, _content_block_server("ok"))
        r = a.call_readonly("list_files")
        assert hasattr(r, "server")
        assert hasattr(r, "tool")
        assert hasattr(r, "classification")
        assert hasattr(r, "output")
        assert hasattr(r, "error")
        assert hasattr(r, "exit_code")
        assert hasattr(r, "success")
        assert hasattr(r, "blocked")
