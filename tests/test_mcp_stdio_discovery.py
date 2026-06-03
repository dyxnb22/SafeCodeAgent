"""Tests for v3.3.2: experimental stdio tools/list discovery.

Uses local stub Python server scripts in tmp_path — no network, no real MCP
server dependency.

Discovery rules under test:
- Success: transport ok + structurally valid tools/list response.
- Empty tools list is still success=True.
- Transport failure → success=False.
- Response result not a JSON object → success=False.
- Missing "tools" key → success=False.
- "tools" not a list → success=False.
- Individual entry: not a dict, missing name, or non-string/empty name → skipped.
- Invalid description/inputSchema types → tolerated with safe defaults.
- Classification is always "unknown".
- server_name is preserved in all schemas.
- Error text never contains argv content or params.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from safecode.mcp.discovery import (
    StdioDiscoveryResult,
    _parse_tool_entry,
    discover_stdio_tools,
)
from safecode.mcp.schema import MCPToolSchema


# ── Stub server helpers ───────────────────────────────────────────────────────


def _write_server(tmp_path: Path, name: str, script: str) -> list[str]:
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return [sys.executable, str(path)]


def _tools_list_server(tools: list) -> str:
    # Embed tools as a double-encoded JSON string so arbitrary JSON values
    # (null, numbers, etc.) are safe in the generated Python script.
    tools_json_str = json.dumps(json.dumps(tools))
    return f"""\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
tools = json.loads({tools_json_str})
print(json.dumps({{"jsonrpc": "2.0", "id": req["id"], "result": {{"tools": tools}}}}))
"""


_EMPTY_TOOLS_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"tools": []}}))
"""

_NO_TOOLS_KEY_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"other": []}}))
"""

_TOOLS_NOT_LIST_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"tools": "not-a-list"}}))
"""

_RESULT_NOT_DICT_SERVER = """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": 42}))
"""

_SLEEP_SERVER = """\
import sys, time
sys.stdin.readline()
time.sleep(60)
"""


# ── StdioDiscoveryResult dataclass ────────────────────────────────────────────


class TestStdioDiscoveryResult:
    def test_success_fields(self):
        r = StdioDiscoveryResult(success=True, schemas=(), error="", skipped_count=0, server_name="s")
        assert r.success is True
        assert r.schemas == ()
        assert r.error == ""
        assert r.skipped_count == 0
        assert r.server_name == "s"

    def test_failure_fields(self):
        r = StdioDiscoveryResult(success=False, schemas=(), error="oops", skipped_count=0, server_name="s")
        assert r.success is False
        assert r.error == "oops"

    def test_is_frozen(self):
        r = StdioDiscoveryResult(success=True, schemas=(), error="", skipped_count=0, server_name="s")
        with pytest.raises(Exception):
            r.success = False  # type: ignore[misc]

    def test_schemas_is_tuple(self):
        schema = MCPToolSchema(server="s", tool="t", classification="unknown")
        r = StdioDiscoveryResult(success=True, schemas=(schema,), error="", skipped_count=0, server_name="s")
        assert isinstance(r.schemas, tuple)
        assert r.schemas[0] is schema


# ── _parse_tool_entry ─────────────────────────────────────────────────────────


class TestParseToolEntry:
    def test_valid_minimal_entry(self):
        result = _parse_tool_entry({"name": "get_files"}, "srv")
        assert result is not None
        assert result.tool == "get_files"
        assert result.server == "srv"
        assert result.classification == "unknown"
        assert result.description == ""
        assert result.args == ()

    def test_valid_with_description(self):
        result = _parse_tool_entry({"name": "list_files", "description": "Lists files"}, "srv")
        assert result is not None
        assert result.description == "Lists files"

    def test_valid_with_input_schema_args(self):
        entry = {
            "name": "read_file",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "encoding": {"type": "string"},
                },
            },
        }
        result = _parse_tool_entry(entry, "srv")
        assert result is not None
        assert set(result.args) == {"path", "encoding"}

    def test_args_are_tuple(self):
        entry = {"name": "t", "inputSchema": {"properties": {"a": {}, "b": {}}}}
        result = _parse_tool_entry(entry, "srv")
        assert result is not None
        assert isinstance(result.args, tuple)

    def test_non_dict_entry_returns_none(self):
        assert _parse_tool_entry("string", "srv") is None
        assert _parse_tool_entry(42, "srv") is None
        assert _parse_tool_entry(None, "srv") is None
        assert _parse_tool_entry(["list"], "srv") is None

    def test_missing_name_returns_none(self):
        assert _parse_tool_entry({"description": "no name"}, "srv") is None

    def test_empty_name_returns_none(self):
        assert _parse_tool_entry({"name": ""}, "srv") is None

    def test_non_string_name_returns_none(self):
        assert _parse_tool_entry({"name": 123}, "srv") is None
        assert _parse_tool_entry({"name": None}, "srv") is None
        assert _parse_tool_entry({"name": ["list"]}, "srv") is None

    def test_non_string_description_defaults_to_empty(self):
        result = _parse_tool_entry({"name": "t", "description": 42}, "srv")
        assert result is not None
        assert result.description == ""

    def test_non_dict_input_schema_ignored(self):
        result = _parse_tool_entry({"name": "t", "inputSchema": "string"}, "srv")
        assert result is not None
        assert result.args == ()

    def test_input_schema_without_properties_gives_empty_args(self):
        result = _parse_tool_entry({"name": "t", "inputSchema": {"type": "object"}}, "srv")
        assert result is not None
        assert result.args == ()

    def test_non_dict_properties_gives_empty_args(self):
        result = _parse_tool_entry({"name": "t", "inputSchema": {"properties": "bad"}}, "srv")
        assert result is not None
        assert result.args == ()

    def test_non_string_property_key_skipped(self):
        # Properties dict with a numeric key (JSON can't have this, but Python dict can)
        result = _parse_tool_entry({"name": "t", "inputSchema": {"properties": {1: {}, "good": {}}}}, "srv")
        assert result is not None
        assert result.args == ("good",)

    def test_server_name_passed_through(self):
        result = _parse_tool_entry({"name": "t"}, "my-server")
        assert result is not None
        assert result.server == "my-server"

    def test_classification_always_unknown(self):
        result = _parse_tool_entry({"name": "write_file"}, "srv")
        assert result is not None
        assert result.classification == "unknown"

    def test_returns_mcp_tool_schema(self):
        result = _parse_tool_entry({"name": "t"}, "srv")
        assert isinstance(result, MCPToolSchema)


# ── discover_stdio_tools: success paths ──────────────────────────────────────


class TestDiscoverStdioToolsSuccess:
    def test_single_tool_discovered(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _tools_list_server([{"name": "get_files"}]))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 1
        assert result.schemas[0].tool == "get_files"

    def test_multiple_tools_discovered(self, tmp_path):
        tools = [{"name": "list_files"}, {"name": "read_file"}, {"name": "search"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 3
        names = {s.tool for s in result.schemas}
        assert names == {"list_files", "read_file", "search"}

    def test_empty_tools_list_is_success(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _EMPTY_TOOLS_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert result.schemas == ()
        assert result.skipped_count == 0
        assert result.error == ""

    def test_success_error_field_empty(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _EMPTY_TOOLS_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert result.error == ""

    def test_server_name_in_schemas(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _tools_list_server([{"name": "t"}]))
        result = discover_stdio_tools("my-server", argv)
        assert result.success is True
        assert result.schemas[0].server == "my-server"

    def test_server_name_on_result(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _EMPTY_TOOLS_SERVER)
        result = discover_stdio_tools("my-server", argv)
        assert result.server_name == "my-server"

    def test_schemas_classification_always_unknown(self, tmp_path):
        tools = [{"name": "write_file"}, {"name": "get_info"}, {"name": "delete_record"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        for schema in result.schemas:
            assert schema.classification == "unknown"

    def test_description_captured(self, tmp_path):
        tools = [{"name": "read_file", "description": "Reads a file safely"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert result.schemas[0].description == "Reads a file safely"

    def test_args_from_input_schema(self, tmp_path):
        tools = [{"name": "read_file", "inputSchema": {"properties": {"path": {}, "encoding": {}}}}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert set(result.schemas[0].args) == {"path", "encoding"}

    def test_returns_stdio_discovery_result(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _EMPTY_TOOLS_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert isinstance(result, StdioDiscoveryResult)

    def test_schemas_is_tuple(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _tools_list_server([{"name": "t"}]))
        result = discover_stdio_tools("srv", argv)
        assert isinstance(result.schemas, tuple)


# ── discover_stdio_tools: transport failure paths ─────────────────────────────


class TestDiscoverStdioToolsTransportFailure:
    def test_timeout_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _SLEEP_SERVER)
        result = discover_stdio_tools("srv", argv, timeout_seconds=0.3)
        assert result.success is False
        assert result.error != ""

    def test_nonexistent_binary_returns_failure(self, tmp_path):
        result = discover_stdio_tools("srv", [str(tmp_path / "no_such_binary")])
        assert result.success is False

    def test_process_exits_no_output_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", """\
import sys
sys.stdin.readline()
sys.exit(1)
""")
        result = discover_stdio_tools("srv", argv)
        assert result.success is False

    def test_non_json_output_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", """\
import sys
sys.stdin.readline()
print("not json at all")
""")
        result = discover_stdio_tools("srv", argv)
        assert result.success is False

    def test_transport_failure_has_error_message(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _SLEEP_SERVER)
        result = discover_stdio_tools("srv", argv, timeout_seconds=0.3)
        assert "transport" in result.error.lower() or "timed out" in result.error.lower() or result.error != ""

    def test_transport_failure_schemas_empty(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _SLEEP_SERVER)
        result = discover_stdio_tools("srv", argv, timeout_seconds=0.3)
        assert result.schemas == ()

    def test_transport_failure_skipped_count_zero(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _SLEEP_SERVER)
        result = discover_stdio_tools("srv", argv, timeout_seconds=0.3)
        assert result.skipped_count == 0


# ── discover_stdio_tools: structural failure paths ────────────────────────────


class TestDiscoverStdioToolsStructuralFailure:
    def test_result_not_dict_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _RESULT_NOT_DICT_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert result.success is False
        assert "object" in result.error.lower() or "dict" in result.error.lower() or result.error != ""

    def test_missing_tools_key_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _NO_TOOLS_KEY_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert result.success is False
        assert "tools" in result.error.lower()

    def test_tools_not_list_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _TOOLS_NOT_LIST_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert result.success is False
        assert "list" in result.error.lower() or "tools" in result.error.lower()

    def test_tools_is_dict_returns_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"tools": {"name": "t"}}}))
""")
        result = discover_stdio_tools("srv", argv)
        assert result.success is False

    def test_structural_failure_schemas_empty(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _NO_TOOLS_KEY_SERVER)
        result = discover_stdio_tools("srv", argv)
        assert result.schemas == ()

    def test_server_name_preserved_on_failure(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _NO_TOOLS_KEY_SERVER)
        result = discover_stdio_tools("my-srv", argv)
        assert result.server_name == "my-srv"


# ── discover_stdio_tools: malformed entry skipping ───────────────────────────


class TestDiscoverStdioToolsMalformedEntries:
    def test_non_dict_entry_skipped(self, tmp_path):
        tools = [{"name": "good"}, "string-entry", {"name": "also-good"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 2
        assert result.skipped_count == 1

    def test_missing_name_entry_skipped(self, tmp_path):
        tools = [{"name": "good"}, {"description": "no name"}, {"name": "also-good"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 2
        assert result.skipped_count == 1

    def test_non_string_name_entry_skipped(self, tmp_path):
        tools = [{"name": 42}, {"name": "valid"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 1
        assert result.skipped_count == 1

    def test_empty_name_entry_skipped(self, tmp_path):
        tools = [{"name": ""}, {"name": "valid"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 1
        assert result.skipped_count == 1

    def test_null_entry_skipped(self, tmp_path):
        tools = [None, {"name": "valid"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 1
        assert result.skipped_count == 1

    def test_all_entries_skipped_is_still_success(self, tmp_path):
        tools = [{"description": "no name"}, "string", 42]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert result.schemas == ()
        assert result.skipped_count == 3

    def test_mixed_valid_and_skipped(self, tmp_path):
        tools = [
            {"name": "good-1"},
            {"description": "no name"},
            {"name": "good-2"},
            "not-a-dict",
            {"name": "good-3"},
        ]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 3
        assert result.skipped_count == 2

    def test_bad_description_type_tolerated(self, tmp_path):
        tools = [{"name": "t", "description": 99}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert len(result.schemas) == 1
        assert result.schemas[0].description == ""
        assert result.skipped_count == 0

    def test_bad_input_schema_type_tolerated(self, tmp_path):
        tools = [{"name": "t", "inputSchema": "not-a-dict"}]
        argv = _write_server(tmp_path, "srv.py", _tools_list_server(tools))
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert result.schemas[0].args == ()
        assert result.skipped_count == 0


# ── Security: error text must not contain argv or secret values ───────────────


class TestDiscoverStdioToolsSecurity:
    def test_timeout_error_does_not_contain_argv(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _SLEEP_SERVER)
        secret_in_argv = argv + ["--secret-arg=sk-abc123-secret"]
        result = discover_stdio_tools("srv", secret_in_argv, timeout_seconds=0.3)
        assert result.success is False
        assert "sk-abc123-secret" not in result.error

    def test_transport_error_does_not_contain_binary_path(self, tmp_path):
        secret_path = str(tmp_path / "sk-secret-binary")
        result = discover_stdio_tools("srv", [secret_path])
        assert result.success is False
        assert "sk-secret-binary" not in result.error

    def test_structural_error_does_not_contain_server_name(self, tmp_path):
        argv = _write_server(tmp_path, "srv.py", _NO_TOOLS_KEY_SERVER)
        result = discover_stdio_tools("secret-server-name-xyz", argv)
        assert result.success is False
        # server_name is in the result field but must not bleed into error text
        assert "secret-server-name-xyz" not in result.error

    def test_no_params_sent_to_server(self, tmp_path):
        # Verify server receives tools/list with no params field
        argv = _write_server(tmp_path, "srv.py", """\
import sys, json
line = sys.stdin.readline()
req = json.loads(line)
has_params = "params" in req
tools = [{"name": "has_params_was_" + str(has_params).lower()}]
print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"tools": tools}}))
""")
        result = discover_stdio_tools("srv", argv)
        assert result.success is True
        assert result.schemas[0].tool == "has_params_was_false"


# ── Existing static MCPDiscovery behavior preserved ──────────────────────────


class TestExistingDiscoveryUnchanged:
    def test_mcp_discovery_class_unchanged(self, tmp_path):
        from safecode.mcp.discovery import MCPDiscovery, MCPTool

        d = MCPDiscovery(tmp_path)
        tools = d.list_tools()
        assert isinstance(tools, list)

    def test_mcp_discovery_write_still_blocked(self, tmp_path):
        from safecode.mcp.discovery import MCPDiscovery

        d = MCPDiscovery(tmp_path)
        with pytest.raises(PermissionError):
            d.assert_write_allowed()

    def test_mcp_tool_placeholder_intact(self):
        from safecode.mcp.discovery import MCPTool

        t = MCPTool(server="s", name="n", risk="low")
        assert t.server == "s"
        assert t.name == "n"
        assert t.risk == "low"
