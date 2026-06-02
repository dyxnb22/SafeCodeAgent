"""Typed MCP tool schema metadata (experimental).

Provides static schema hints that augment keyword-based read/write
classification in ``safecode.mcp.runner.classify_mcp_tool``.

Status: experimental. This module provides typed metadata without
implementing real MCP JSON-RPC. Schema metadata is optional — when absent,
``classify_mcp_tool`` falls back to keyword matching unchanged.

Usage::

    from safecode.mcp.schema import MCPToolSchema, classify_with_schema

    schema = MCPToolSchema(server="myserver", tool="sync_files", classification="write")
    classify_with_schema("sync_files", [schema])  # returns "write" from schema
    classify_with_schema("unknown_tool", [])       # falls back to keyword matching
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# Classification values mirror those returned by classify_mcp_tool.
MCPClassification = Literal["read", "write", "unknown"]


@dataclass(frozen=True)
class MCPToolSchema:
    """Static metadata for one MCP tool.

    Used to provide explicit classification without relying on keyword
    matching, for tools whose names are ambiguous or misleading.

    Fields
    ------
    server:
        MCP server name as configured in ``.sac/mcp.toml``.
    tool:
        Tool name on that server.
    classification:
        Explicit read/write/unknown label. Overrides keyword matching
        when present.
    description:
        Optional human-readable description of the tool.
    args:
        Optional list of argument names the tool accepts.
    """

    server: str
    tool: str
    classification: MCPClassification
    description: str = ""
    args: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MCPSchemaStore:
    """Registry of static MCP tool schemas.

    This is a simple in-memory store. It does not persist, contact MCP
    servers, or perform any I/O. Schemas are added at construction time.
    """

    schemas: tuple[MCPToolSchema, ...] = field(default_factory=tuple)

    def lookup(self, tool: str, server: str = "") -> MCPToolSchema | None:
        """Return the first schema matching *tool* (and optionally *server*).

        If *server* is empty, matches on *tool* name alone.
        Returns ``None`` when no match is found.
        """
        for schema in self.schemas:
            if schema.tool == tool:
                if not server or schema.server == server:
                    return schema
        return None

    def classify(self, tool: str, server: str = "") -> MCPClassification | None:
        """Return the explicit classification if a matching schema exists.

        Returns ``None`` when no schema is found, signalling that the
        caller should fall back to keyword matching.
        """
        schema = self.lookup(tool, server)
        return schema.classification if schema is not None else None

    def tools_list(self, server: str = "") -> list[MCPToolSchema]:
        """Return schemas for *server* (or all schemas when *server* is empty).

        Order matches insertion order within the store. No I/O is performed.
        """
        if not server:
            return list(self.schemas)
        return [s for s in self.schemas if s.server == server]

    def classify_all(self, server: str = "") -> dict[str, str]:
        """Return a tool→classification mapping for *server* (or all servers).

        Tools appearing multiple times (different servers) are deduplicated by
        last write when *server* is empty.  When *server* is set, only schemas
        for that server are included.
        """
        result: dict[str, str] = {}
        for schema in self.tools_list(server):
            result[schema.tool] = schema.classification
        return result


def classify_with_schema(
    tool_name: str,
    schemas: list[MCPToolSchema],
    *,
    server: str = "",
) -> str:
    """Classify a tool name using static schemas first, then keyword fallback.

    If any schema in *schemas* matches *tool_name* (and *server* when
    provided), its explicit classification is returned. Otherwise
    ``classify_mcp_tool`` is called as a keyword-based fallback.

    This function is the recommended entry point when schema metadata
    may be available.

    Parameters
    ----------
    tool_name:
        The tool name to classify.
    schemas:
        List of ``MCPToolSchema`` objects. May be empty.
    server:
        Optional server constraint. When empty, matches on tool name only.

    Returns
    -------
    str
        One of ``"read"``, ``"write"``, or ``"unknown"``.
    """
    from safecode.mcp.runner import classify_mcp_tool

    store = MCPSchemaStore(schemas=tuple(schemas))
    explicit = store.classify(tool_name, server)
    if explicit is not None:
        return explicit
    return classify_mcp_tool(tool_name)
