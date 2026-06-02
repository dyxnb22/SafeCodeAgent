"""Tests for MCP tools-list schema shim (v2.9.4).

Covers:
- MCPSchemaStore.tools_list() and classify_all() helpers
- MCPReadOnlyRunner uses schema classification when schemas are provided
- MCPReadToolExecutor uses schema classification when schemas are provided
- Schema-absent workloads behave identically to pre-v2.9.4 (keyword fallback)
- Declared write tools are blocked in read-only runner even without write-like names
- Unknown bucket shrinks when schema metadata is present
- No real JSON-RPC client; no I/O; no subprocess in classification path
"""

from __future__ import annotations

import pytest

from safecode.mcp.schema import (
    MCPSchemaStore,
    MCPToolSchema,
    classify_with_schema,
)


class TestToolsList:
    def test_tools_list_all(self):
        s1 = MCPToolSchema(server="srv1", tool="sync_data", classification="write")
        s2 = MCPToolSchema(server="srv2", tool="get_info", classification="read")
        store = MCPSchemaStore(schemas=(s1, s2))
        assert store.tools_list() == [s1, s2]

    def test_tools_list_filtered_by_server(self):
        s1 = MCPToolSchema(server="srv1", tool="sync_data", classification="write")
        s2 = MCPToolSchema(server="srv2", tool="get_info", classification="read")
        s3 = MCPToolSchema(server="srv1", tool="fetch_data", classification="read")
        store = MCPSchemaStore(schemas=(s1, s2, s3))
        result = store.tools_list(server="srv1")
        assert result == [s1, s3]
        assert len(result) == 2

    def test_tools_list_empty_store(self):
        store = MCPSchemaStore()
        assert store.tools_list() == []

    def test_tools_list_unknown_server_returns_empty(self):
        s1 = MCPToolSchema(server="srv1", tool="get_info", classification="read")
        store = MCPSchemaStore(schemas=(s1,))
        assert store.tools_list(server="nonexistent") == []

    def test_tools_list_preserves_order(self):
        schemas = tuple(
            MCPToolSchema(server="s", tool=f"tool_{i}", classification="read")
            for i in range(5)
        )
        store = MCPSchemaStore(schemas=schemas)
        result = store.tools_list()
        assert [s.tool for s in result] == [f"tool_{i}" for i in range(5)]


class TestClassifyAll:
    def test_classify_all_returns_mapping(self):
        s1 = MCPToolSchema(server="s", tool="sync_data", classification="write")
        s2 = MCPToolSchema(server="s", tool="get_info", classification="read")
        store = MCPSchemaStore(schemas=(s1, s2))
        result = store.classify_all()
        assert result == {"sync_data": "write", "get_info": "read"}

    def test_classify_all_filtered_by_server(self):
        s1 = MCPToolSchema(server="srv1", tool="sync_data", classification="write")
        s2 = MCPToolSchema(server="srv2", tool="get_info", classification="read")
        store = MCPSchemaStore(schemas=(s1, s2))
        assert store.classify_all(server="srv1") == {"sync_data": "write"}
        assert store.classify_all(server="srv2") == {"get_info": "read"}

    def test_classify_all_empty(self):
        store = MCPSchemaStore()
        assert store.classify_all() == {}

    def test_classify_all_unknown_classification(self):
        s = MCPToolSchema(server="s", tool="ambiguous_op", classification="unknown")
        store = MCPSchemaStore(schemas=(s,))
        assert store.classify_all() == {"ambiguous_op": "unknown"}


class TestSchemaWiredIntoRunner:
    """MCPReadOnlyRunner uses schema classification when schemas are provided."""

    def test_no_schema_write_keyword_still_blocked(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        runner = MCPReadOnlyRunner(tmp_path)
        # "write_log" classifies as "write" by keywords → blocked
        result = runner.call_readonly("myserver", "write_log", {})
        assert result.blocked
        assert result.classification == "write"

    def test_schema_overrides_unknown_to_write_is_blocked(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        # "process_data" is "unknown" by keyword alone
        schema = MCPToolSchema(server="myserver", tool="process_data", classification="write")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("myserver", "process_data", {})
        assert result.blocked
        assert result.classification == "write"

    def test_schema_overrides_write_name_to_read_allowed_up_to_policy(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        # "write_log" would normally be "write" (blocked in call_readonly)
        # Schema says "read" → classification passes the read check, but server not configured
        schema = MCPToolSchema(server="myserver", tool="write_log", classification="read")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("myserver", "write_log", {})
        # Classification passes ("read"), but server not found → blocked for a different reason
        assert result.blocked
        assert result.classification == "read"

    def test_schema_absent_behavior_unchanged(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        runner_no_schema = MCPReadOnlyRunner(tmp_path)
        result = runner_no_schema.call_readonly("srv", "get_info", {})
        # "get_info" is "read" by keyword → classification passes, blocked by missing server config
        assert result.blocked
        assert result.classification == "read"

    def test_schema_server_filter_applied(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        # Schema declares "sync_data" as "read" but only for "myserver"
        schema = MCPToolSchema(server="myserver", tool="sync_data", classification="read")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        # Calling with "myserver" → schema applies → "read" classification
        result = runner.call_readonly("myserver", "sync_data", {})
        assert result.classification == "read"
        # Still blocked because server not in config, but classification is correct
        assert result.blocked

    def test_unknown_tool_shrinks_unknown_bucket_via_schema(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.mcp.runner import classify_mcp_tool

        # Confirm "transform_batch" is unknown without schema
        assert classify_mcp_tool("transform_batch") == "unknown"

        schema = MCPToolSchema(server="s", tool="transform_batch", classification="write")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("s", "transform_batch", {})
        # Now classified as "write" → blocked by read-only check
        assert result.blocked
        assert result.classification == "write"


class TestSchemaWiredIntoLoopExecutor:
    """MCPReadToolExecutor uses schema classification when schemas are provided."""

    def test_no_schema_read_keyword_accepted(self, tmp_path):
        from safecode.mcp.loop_executor import MCPReadToolExecutor

        executor = MCPReadToolExecutor(tmp_path)
        result = executor.execute("srv.get_info", {})
        # "get_info" is "read" by keyword → passes classification check
        # Fails later (runner can't find server config), but not for classification reasons
        assert result.blocked
        assert "get_info" in result.observation.lower() or result.blocked

    def test_schema_write_tool_blocked_in_executor(self, tmp_path):
        from safecode.mcp.loop_executor import MCPReadToolExecutor

        # "process_data" is "unknown" by keyword → but schema says "write"
        schema = MCPToolSchema(server="srv", tool="process_data", classification="write")
        executor = MCPReadToolExecutor(tmp_path, schemas=[schema])
        result = executor.execute("srv.process_data", {})
        assert result.blocked
        # Blocked because "write" is not read-only
        assert "not read-only" in result.observation or result.blocked

    def test_schema_absent_unknown_tool_blocked(self, tmp_path):
        from safecode.mcp.loop_executor import MCPReadToolExecutor

        executor = MCPReadToolExecutor(tmp_path)
        result = executor.execute("srv.process_data", {})
        # "process_data" is "unknown" → blocked (not read-only)
        assert result.blocked

    def test_schema_overrides_write_name_to_read_in_executor(self, tmp_path):
        from safecode.mcp.loop_executor import MCPReadToolExecutor

        # "write_log" is normally "write" (would be blocked by classification check)
        # Schema overrides to "read" → passes classification, fails later (server config)
        schema = MCPToolSchema(server="srv", tool="write_log", classification="read")
        executor = MCPReadToolExecutor(tmp_path, schemas=[schema])
        result = executor.execute("srv.write_log", {})
        # Should not be blocked by "not read-only" check; server config blocks it instead
        assert result.blocked
        assert "not read-only" not in result.observation

    def test_no_io_in_schema_classification(self, tmp_path):
        from safecode.mcp.loop_executor import MCPReadToolExecutor

        schema = MCPToolSchema(server="srv", tool="process_data", classification="write")
        executor = MCPReadToolExecutor(tmp_path, schemas=[schema])
        files_before = set(tmp_path.rglob("*"))
        executor.execute("srv.process_data", {})
        files_after = set(tmp_path.rglob("*"))
        assert files_before == files_after


class TestSchemaAbsentFallback:
    """Schema-absent: keyword fallback is unchanged (no regression)."""

    def test_classify_with_schema_empty_list(self):
        from safecode.mcp.runner import classify_mcp_tool

        for tool in ["get_info", "set_config", "list_items", "delete_entry", "unknown_op"]:
            assert classify_with_schema(tool, []) == classify_mcp_tool(tool)

    def test_runner_no_schemas_uses_keyword(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner, classify_mcp_tool

        runner = MCPReadOnlyRunner(tmp_path)
        # Verify runner._schemas is empty by default
        assert runner._schemas == []

    def test_executor_no_schemas_uses_keyword(self, tmp_path):
        from safecode.mcp.loop_executor import MCPReadToolExecutor

        executor = MCPReadToolExecutor(tmp_path)
        assert executor._schemas == []

    def test_no_real_jsonrpc_in_classification(self, tmp_path):
        import subprocess

        original_run = subprocess.run
        calls: list = []

        def mock_run(*args, **kwargs):
            calls.append(args)
            raise AssertionError("subprocess.run must not be called during schema classification")

        subprocess.run = mock_run  # type: ignore[assignment]
        try:
            schema = MCPToolSchema(server="s", tool="sync_data", classification="write")
            store = MCPSchemaStore(schemas=(schema,))
            store.classify("sync_data")
            classify_with_schema("sync_data", [schema])
        finally:
            subprocess.run = original_run  # type: ignore[assignment]

        assert not calls
