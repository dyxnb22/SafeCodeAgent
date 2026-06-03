"""Tests for v3.3.3: merge_discovered_schemas.

Covers: classification conflict (static wins), metadata fill-in
(description and args), empty discovery, empty static, discovered-only
tools appended, duplicate handling, arg_schemas preservation, ordering,
and purity (no I/O, no subprocess).
"""

from __future__ import annotations

import subprocess

import pytest

from safecode.mcp.schema import (
    MCPSchemaArg,
    MCPSchemaStore,
    MCPToolSchema,
    merge_discovered_schemas,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _static(tool: str, classification: str = "read", *, server: str = "srv",
            description: str = "", args: tuple[str, ...] = ()) -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification=classification,
                         description=description, args=args)


def _disc(tool: str, *, server: str = "srv", description: str = "",
          args: tuple[str, ...] = ()) -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification="unknown",
                         description=description, args=args)


# ── Return type and purity ────────────────────────────────────────────────────


class TestMergeReturnType:
    def test_returns_tuple(self):
        result = merge_discovered_schemas((), ())
        assert isinstance(result, tuple)

    def test_both_empty_returns_empty_tuple(self):
        result = merge_discovered_schemas((), ())
        assert result == ()

    def test_does_not_mutate_static(self):
        static = (_static("get_files", "read"),)
        original_id = id(static[0])
        merge_discovered_schemas(static, (_disc("get_files"),))
        assert id(static[0]) == original_id

    def test_does_not_mutate_discovered(self):
        disc = (_disc("get_files"),)
        original_id = id(disc[0])
        merge_discovered_schemas((_static("get_files", "read"),), disc)
        assert id(disc[0]) == original_id

    def test_returns_mcp_tool_schema_objects(self):
        result = merge_discovered_schemas((_static("t"),), ())
        for s in result:
            assert isinstance(s, MCPToolSchema)

    def test_no_io(self, tmp_path):
        merge_discovered_schemas((_static("t"),), (_disc("t"),))
        assert not list(tmp_path.iterdir())

    def test_no_subprocess(self, monkeypatch):
        calls: list[object] = []
        original = subprocess.run

        def mock_run(*args, **kwargs):  # type: ignore[override]
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)
        merge_discovered_schemas((_static("t"),), (_disc("t"),))
        assert not calls


# ── Empty inputs ──────────────────────────────────────────────────────────────


class TestMergeEmptyInputs:
    def test_empty_discovery_returns_static_unchanged(self):
        static = (_static("get_files", "read"), _static("write_file", "write"))
        result = merge_discovered_schemas(static, ())
        assert result == static

    def test_empty_static_returns_discovered(self):
        disc = (_disc("get_files"), _disc("read_config"))
        result = merge_discovered_schemas((), disc)
        assert set(s.tool for s in result) == {"get_files", "read_config"}

    def test_empty_static_discovered_classification_unchanged(self):
        disc = (_disc("get_files"),)
        result = merge_discovered_schemas((), disc)
        assert result[0].classification == "unknown"

    def test_empty_static_schemas_is_empty_tuple(self):
        result = merge_discovered_schemas((), ())
        assert result == ()


# ── Classification conflict: static wins ─────────────────────────────────────


class TestMergeClassificationConflict:
    def test_static_read_wins_over_discovered_unknown(self):
        result = merge_discovered_schemas(
            (_static("get_files", "read"),),
            (_disc("get_files"),),
        )
        assert result[0].classification == "read"

    def test_static_write_wins_over_discovered_unknown(self):
        result = merge_discovered_schemas(
            (_static("write_file", "write"),),
            (_disc("write_file"),),
        )
        assert result[0].classification == "write"

    def test_static_unknown_kept_as_unknown(self):
        result = merge_discovered_schemas(
            (_static("process", "unknown"),),
            (_disc("process"),),
        )
        assert result[0].classification == "unknown"

    def test_classification_not_overwritten_when_no_fill(self):
        result = merge_discovered_schemas(
            (_static("get_files", "read", description="Static desc", args=("path",)),),
            (_disc("get_files", description="Disc desc", args=("path",)),),
        )
        assert result[0].classification == "read"

    def test_multiple_tools_classification_preserved(self):
        static = (
            _static("get_files", "read"),
            _static("write_file", "write"),
            _static("process", "unknown"),
        )
        disc = (
            _disc("get_files"),
            _disc("write_file"),
            _disc("process"),
        )
        result = merge_discovered_schemas(static, disc)
        by_tool = {s.tool: s.classification for s in result}
        assert by_tool == {"get_files": "read", "write_file": "write", "process": "unknown"}


# ── Metadata fill-in: description ────────────────────────────────────────────


class TestMergeDescriptionFill:
    def test_discovered_fills_empty_static_description(self):
        result = merge_discovered_schemas(
            (_static("get_files", description=""),),
            (_disc("get_files", description="Reads files from the project"),),
        )
        assert result[0].description == "Reads files from the project"

    def test_static_description_kept_when_non_empty(self):
        result = merge_discovered_schemas(
            (_static("get_files", description="Static description"),),
            (_disc("get_files", description="Discovered description"),),
        )
        assert result[0].description == "Static description"

    def test_empty_discovered_description_does_not_overwrite(self):
        result = merge_discovered_schemas(
            (_static("get_files", description="Static"),),
            (_disc("get_files", description=""),),
        )
        assert result[0].description == "Static"

    def test_both_empty_description_stays_empty(self):
        result = merge_discovered_schemas(
            (_static("get_files", description=""),),
            (_disc("get_files", description=""),),
        )
        assert result[0].description == ""

    def test_fill_preserves_classification(self):
        result = merge_discovered_schemas(
            (_static("get_files", "read", description=""),),
            (_disc("get_files", description="Discovered"),),
        )
        assert result[0].classification == "read"
        assert result[0].description == "Discovered"


# ── Metadata fill-in: args ────────────────────────────────────────────────────


class TestMergeArgsFill:
    def test_discovered_fills_empty_static_args(self):
        result = merge_discovered_schemas(
            (_static("get_files", args=()),),
            (_disc("get_files", args=("path", "limit")),),
        )
        assert set(result[0].args) == {"path", "limit"}

    def test_static_args_kept_when_non_empty(self):
        result = merge_discovered_schemas(
            (_static("get_files", args=("path",)),),
            (_disc("get_files", args=("path", "limit")),),
        )
        assert result[0].args == ("path",)

    def test_empty_discovered_args_do_not_overwrite_static(self):
        result = merge_discovered_schemas(
            (_static("get_files", args=("path",)),),
            (_disc("get_files", args=()),),
        )
        assert result[0].args == ("path",)

    def test_both_empty_args_stays_empty(self):
        result = merge_discovered_schemas(
            (_static("get_files", args=()),),
            (_disc("get_files", args=()),),
        )
        assert result[0].args == ()

    def test_fill_args_preserves_classification(self):
        result = merge_discovered_schemas(
            (_static("get_files", "write", args=()),),
            (_disc("get_files", args=("path",)),),
        )
        assert result[0].classification == "write"
        assert "path" in result[0].args


# ── arg_schemas preserved from static ────────────────────────────────────────


class TestMergeArgSchemas:
    def test_arg_schemas_preserved_after_metadata_fill(self):
        arg_schema = MCPSchemaArg(name="path", type_name="string", required=True)
        static_schema = MCPToolSchema(
            server="srv", tool="get_files", classification="read",
            description="", args=(), arg_schemas=(arg_schema,),
        )
        disc_schema = _disc("get_files", description="Filled", args=("path",))
        result = merge_discovered_schemas((static_schema,), (disc_schema,))
        assert len(result) == 1
        assert result[0].arg_schemas == (arg_schema,)

    def test_static_no_arg_schemas_gives_empty_after_fill(self):
        result = merge_discovered_schemas(
            (_static("get_files", description=""),),
            (_disc("get_files", description="Filled"),),
        )
        assert result[0].arg_schemas == ()

    def test_discovered_only_tool_has_no_arg_schemas(self):
        result = merge_discovered_schemas((), (_disc("new_tool"),))
        assert result[0].arg_schemas == ()


# ── Discovered-only tools appended ───────────────────────────────────────────


class TestMergeDiscoveredOnlyTools:
    def test_discovered_only_tool_appended(self):
        result = merge_discovered_schemas(
            (_static("existing"),),
            (_disc("new_tool"),),
        )
        tools = [s.tool for s in result]
        assert "new_tool" in tools

    def test_discovered_only_classification_remains_unknown(self):
        result = merge_discovered_schemas((), (_disc("new_tool"),))
        assert result[0].classification == "unknown"

    def test_multiple_discovered_only_all_appended(self):
        result = merge_discovered_schemas(
            (),
            (_disc("a"), _disc("b"), _disc("c")),
        )
        assert len(result) == 3
        assert {s.tool for s in result} == {"a", "b", "c"}

    def test_discovered_only_server_preserved(self):
        result = merge_discovered_schemas((), (_disc("t", server="other-srv"),))
        assert result[0].server == "other-srv"


# ── Order guarantees ──────────────────────────────────────────────────────────


class TestMergeOrdering:
    def test_static_order_preserved(self):
        static = (_static("c"), _static("a"), _static("b"))
        result = merge_discovered_schemas(static, ())
        assert [s.tool for s in result] == ["c", "a", "b"]

    def test_enriched_static_before_discovered_only(self):
        result = merge_discovered_schemas(
            (_static("static-tool"),),
            (_disc("static-tool", description="Fill"), _disc("discovered-only")),
        )
        assert result[0].tool == "static-tool"
        assert result[1].tool == "discovered-only"

    def test_discovered_only_appended_in_discovery_order(self):
        result = merge_discovered_schemas(
            (),
            (_disc("z"), _disc("a"), _disc("m")),
        )
        assert [s.tool for s in result] == ["z", "a", "m"]

    def test_all_static_before_all_discovered_only(self):
        static = (_static("s1"), _static("s2"))
        disc = (_disc("s1"), _disc("s2"), _disc("d1"), _disc("d2"))
        result = merge_discovered_schemas(static, disc)
        tools = [s.tool for s in result]
        assert tools.index("s1") < tools.index("d1")
        assert tools.index("s2") < tools.index("d2")


# ── Duplicate handling ────────────────────────────────────────────────────────


class TestMergeDuplicates:
    def test_duplicate_in_discovered_first_wins(self):
        result = merge_discovered_schemas(
            (),
            (
                _disc("t", description="First"),
                _disc("t", description="Second"),
            ),
        )
        assert len(result) == 1
        assert result[0].description == "First"

    def test_duplicate_in_discovered_only_one_appended(self):
        result = merge_discovered_schemas(
            (_static("existing"),),
            (_disc("new"), _disc("new")),
        )
        assert len(result) == 2  # "existing" + one "new"
        assert sum(1 for s in result if s.tool == "new") == 1

    def test_static_duplicates_preserved(self):
        # Static duplicates are not deduplicated (preserves MCPSchemaStore behavior)
        static = (_static("t", "read", server="srv"), _static("t", "write", server="srv"))
        result = merge_discovered_schemas(static, ())
        assert len(result) == 2

    def test_different_servers_not_merged(self):
        result = merge_discovered_schemas(
            (_static("t", server="srv-a"),),
            (_disc("t", server="srv-b"),),
        )
        assert len(result) == 2
        servers = {s.server for s in result}
        assert "srv-a" in servers
        assert "srv-b" in servers


# ── Integration with MCPSchemaStore ──────────────────────────────────────────


class TestMergeWithSchemaStore:
    def test_result_wrappable_in_schema_store(self):
        static = (_static("get_files", "read"),)
        disc = (_disc("get_files", description="Reads files"),)
        merged = merge_discovered_schemas(static, disc)
        store = MCPSchemaStore(schemas=merged)
        assert store.classify("get_files") == "read"

    def test_discovered_only_tool_in_store_classifies_unknown(self):
        merged = merge_discovered_schemas((), (_disc("new_tool"),))
        store = MCPSchemaStore(schemas=merged)
        assert store.classify("new_tool") == "unknown"

    def test_store_lookup_after_merge(self):
        static = (_static("get_files", "read", description=""),)
        disc = (_disc("get_files", description="Fetches files"),)
        merged = merge_discovered_schemas(static, disc)
        store = MCPSchemaStore(schemas=merged)
        schema = store.lookup("get_files")
        assert schema is not None
        assert schema.description == "Fetches files"
        assert schema.classification == "read"

    def test_existing_static_schema_store_classification_unchanged(self):
        static_store = MCPSchemaStore(
            schemas=(_static("write_file", "write"),)
        )
        disc = (_disc("write_file"),)
        merged = merge_discovered_schemas(static_store.schemas, tuple(disc))
        store = MCPSchemaStore(schemas=merged)
        assert store.classify("write_file") == "write"
