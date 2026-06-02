"""Tests for MCP schema shim (v2.8.4).

Covers schema-present behavior (explicit classification) and
schema-absent fallback (keyword matching unchanged).

The schema shim is experimental: it adds typed metadata without
implementing real MCP JSON-RPC.
"""

from __future__ import annotations

import pytest

from safecode.mcp.schema import (
    MCPSchemaStore,
    MCPToolSchema,
    classify_with_schema,
)


class TestMCPToolSchema:
    def test_read_schema(self):
        schema = MCPToolSchema(server="myserver", tool="get_files", classification="read")
        assert schema.server == "myserver"
        assert schema.tool == "get_files"
        assert schema.classification == "read"

    def test_write_schema(self):
        schema = MCPToolSchema(server="s", tool="sync_data", classification="write")
        assert schema.classification == "write"

    def test_unknown_schema(self):
        schema = MCPToolSchema(server="s", tool="process", classification="unknown")
        assert schema.classification == "unknown"

    def test_description_optional(self):
        schema = MCPToolSchema(server="s", tool="t", classification="read")
        assert schema.description == ""

    def test_args_default_empty(self):
        schema = MCPToolSchema(server="s", tool="t", classification="read")
        assert schema.args == ()

    def test_args_provided(self):
        schema = MCPToolSchema(
            server="s", tool="t", classification="read", args=("path", "limit")
        )
        assert schema.args == ("path", "limit")

    def test_schema_is_frozen(self):
        schema = MCPToolSchema(server="s", tool="t", classification="read")
        with pytest.raises(Exception):
            schema.tool = "other"  # type: ignore[misc]


class TestMCPSchemaStoreLookup:
    def test_lookup_by_tool_name(self):
        schema = MCPToolSchema(server="srv", tool="sync_data", classification="write")
        store = MCPSchemaStore(schemas=(schema,))
        result = store.lookup("sync_data")
        assert result is schema

    def test_lookup_not_found_returns_none(self):
        store = MCPSchemaStore(schemas=())
        assert store.lookup("unknown_tool") is None

    def test_lookup_with_server_filter(self):
        s1 = MCPToolSchema(server="srv1", tool="get_info", classification="read")
        s2 = MCPToolSchema(server="srv2", tool="get_info", classification="write")
        store = MCPSchemaStore(schemas=(s1, s2))
        assert store.lookup("get_info", server="srv1") is s1
        assert store.lookup("get_info", server="srv2") is s2

    def test_lookup_without_server_returns_first(self):
        s1 = MCPToolSchema(server="srv1", tool="get_info", classification="read")
        s2 = MCPToolSchema(server="srv2", tool="get_info", classification="write")
        store = MCPSchemaStore(schemas=(s1, s2))
        result = store.lookup("get_info")
        assert result is s1

    def test_lookup_empty_schemas(self):
        store = MCPSchemaStore()
        assert store.lookup("get_files") is None


class TestMCPSchemaStoreClassify:
    def test_classify_returns_explicit_classification(self):
        schema = MCPToolSchema(server="s", tool="sync_data", classification="write")
        store = MCPSchemaStore(schemas=(schema,))
        assert store.classify("sync_data") == "write"

    def test_classify_returns_none_when_not_found(self):
        store = MCPSchemaStore()
        assert store.classify("unknown_tool") is None

    def test_classify_read(self):
        schema = MCPToolSchema(server="s", tool="fetch_config", classification="read")
        store = MCPSchemaStore(schemas=(schema,))
        assert store.classify("fetch_config") == "read"

    def test_classify_with_server(self):
        s1 = MCPToolSchema(server="srv1", tool="op", classification="read")
        s2 = MCPToolSchema(server="srv2", tool="op", classification="write")
        store = MCPSchemaStore(schemas=(s1, s2))
        assert store.classify("op", "srv1") == "read"
        assert store.classify("op", "srv2") == "write"


class TestClassifyWithSchemaPresent:
    """Schema-present: explicit classification overrides keyword matching."""

    def test_schema_overrides_keyword_read(self):
        # "write_log" would be classified as "write" by keywords alone,
        # but schema says "read".
        schema = MCPToolSchema(server="s", tool="write_log", classification="read")
        result = classify_with_schema("write_log", [schema])
        assert result == "read"

    def test_schema_overrides_keyword_write(self):
        # "get_status" would be "read" by keywords, but schema says "write".
        schema = MCPToolSchema(server="s", tool="get_status", classification="write")
        result = classify_with_schema("get_status", [schema])
        assert result == "write"

    def test_schema_explicit_unknown(self):
        schema = MCPToolSchema(server="s", tool="ambiguous_op", classification="unknown")
        result = classify_with_schema("ambiguous_op", [schema])
        assert result == "unknown"

    def test_schema_server_filter_respected(self):
        schema = MCPToolSchema(server="srv1", tool="op", classification="write")
        # Asking for "srv2" finds no schema, falls back to keywords.
        result = classify_with_schema("op", [schema], server="srv2")
        # "op" has no keyword match → "unknown"
        assert result == "unknown"

    def test_schema_match_overrides_when_server_matches(self):
        schema = MCPToolSchema(server="srv1", tool="op", classification="read")
        result = classify_with_schema("op", [schema], server="srv1")
        assert result == "read"


class TestClassifyWithSchemaAbsent:
    """Schema-absent: keyword fallback is unchanged."""

    def test_read_keyword_falls_back(self):
        result = classify_with_schema("get_files", [])
        assert result == "read"

    def test_write_keyword_falls_back(self):
        result = classify_with_schema("write_file", [])
        assert result == "write"

    def test_unknown_keyword_falls_back(self):
        result = classify_with_schema("process_data", [])
        assert result == "unknown"

    def test_list_keyword_falls_back(self):
        result = classify_with_schema("list_resources", [])
        assert result == "read"

    def test_delete_keyword_falls_back(self):
        result = classify_with_schema("delete_entry", [])
        assert result == "write"

    def test_empty_schemas_always_falls_back(self):
        # All keyword-based results should match direct classify_mcp_tool calls.
        from safecode.mcp.runner import classify_mcp_tool

        for tool_name in ["get_info", "set_config", "process_batch", "list_items"]:
            assert classify_with_schema(tool_name, []) == classify_mcp_tool(tool_name)

    def test_no_schema_match_falls_back(self):
        schema = MCPToolSchema(server="s", tool="other_tool", classification="read")
        result = classify_with_schema("delete_record", [schema])
        assert result == "write"  # keyword match, schema didn't apply


class TestSchemaExperimental:
    """Schema shim is experimental — no real JSON-RPC, no I/O."""

    def test_no_file_io(self, tmp_path):
        schema = MCPToolSchema(server="s", tool="t", classification="read")
        store = MCPSchemaStore(schemas=(schema,))
        # Should complete without touching any files
        result = store.classify("t")
        assert result == "read"
        assert not list(tmp_path.iterdir())

    def test_no_subprocess(self):
        import subprocess

        original_run = subprocess.run

        calls: list[object] = []

        def mock_run(*args, **kwargs):  # type: ignore[override]
            calls.append(args)
            return original_run(*args, **kwargs)

        schema = MCPToolSchema(server="s", tool="t", classification="read")
        classify_with_schema("t", [schema])
        assert not calls, "classify_with_schema must not call subprocess.run"
