"""Typed MCP tool schema metadata (experimental).

Provides static schema hints that augment keyword-based read/write
classification in ``safecode.mcp.runner.classify_mcp_tool``.

Status: experimental. This module provides typed metadata without
implementing real MCP JSON-RPC. Schema metadata is optional — when absent,
``classify_mcp_tool`` falls back to keyword matching unchanged.

Usage::

    from safecode.mcp.schema import MCPToolSchema, MCPSchemaArg, classify_with_schema

    schema = MCPToolSchema(server="myserver", tool="sync_files", classification="write")
    classify_with_schema("sync_files", [schema])  # returns "write" from schema
    classify_with_schema("unknown_tool", [])       # falls back to keyword matching
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# Classification values mirror those returned by classify_mcp_tool.
MCPClassification = Literal["read", "write", "unknown"]


@dataclass(frozen=True)
class MCPSchemaArg:
    """Typed metadata for one argument of an MCP tool.

    When ``arg_schemas`` is non-empty on the parent ``MCPToolSchema``,
    ``validate_call_args`` uses these to enforce required args and reject
    extra args.  Schema-less callers are never affected.

    Fields
    ------
    name:
        Argument name as expected by the tool.
    type_name:
        Expected type as a string (``"string"``, ``"integer"``, ``"boolean"``,
        ``"object"``, ``"array"``). Used for informational validation only.
    required:
        Whether the argument must be present in every call.
    """

    name: str
    type_name: str = "string"
    required: bool = False


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
        Optional list of argument names the tool accepts (legacy string form).
    arg_schemas:
        Optional typed argument metadata. When non-empty, ``validate_call_args``
        enforces required args and rejects extra args.
    """

    server: str
    tool: str
    classification: MCPClassification
    description: str = ""
    args: tuple[str, ...] = field(default_factory=tuple)
    arg_schemas: tuple[MCPSchemaArg, ...] = field(default_factory=tuple)


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


def validate_call_args(
    tool_schema: MCPToolSchema,
    call_args: dict[str, Any],
) -> str | None:
    """Validate *call_args* against *tool_schema.arg_schemas*.

    Returns an error string when validation fails, or ``None`` when
    the call is valid (or when *arg_schemas* is empty, meaning no validation
    is performed).

    Rules when ``arg_schemas`` is non-empty:
    - Required args must be present in *call_args*.
    - Extra args (keys not declared in ``arg_schemas``) are rejected.

    Schema-less workloads (``arg_schemas == ()``) are never affected.

    Parameters
    ----------
    tool_schema:
        Schema to validate against.
    call_args:
        Argument dict from the caller.

    Returns
    -------
    str | None
        Error message if invalid; ``None`` if valid or no arg schema.
    """
    if not tool_schema.arg_schemas:
        return None

    declared_names = {a.name for a in tool_schema.arg_schemas}
    required_names = {a.name for a in tool_schema.arg_schemas if a.required}

    missing = required_names - call_args.keys()
    if missing:
        names = ", ".join(sorted(missing))
        return f"Missing required argument(s): {names}"

    extra = call_args.keys() - declared_names
    if extra:
        names = ", ".join(sorted(extra))
        return f"Unexpected argument(s) not in schema: {names}"

    return None


def merge_discovered_schemas(
    static: tuple[MCPToolSchema, ...],
    discovered: tuple[MCPToolSchema, ...],
) -> tuple[MCPToolSchema, ...]:
    """Merge discovered stdio schemas with existing static schemas (experimental, v3.3.3).

    Pure helper — no I/O, no subprocess calls, no side effects.

    Merge rules
    -----------
    Matching is by ``(server, tool)`` pair.

    For tools present in both *static* and *discovered*:

    - **Classification**: static always wins.  Discovered classification
      (always ``"unknown"``) never overwrites an explicit static value.
    - **description**: static value kept when non-empty; discovered value
      used to fill in when static is ``""``.
    - **args**: static value kept when non-empty; discovered value used to
      fill in when static ``args`` is ``()``.
    - **arg_schemas**: always from static; discovered never supplies typed
      arg schemas.

    For tools present only in *static*: included as-is.

    For tools present only in *discovered*: appended as-is (classification
    remains ``"unknown"``).

    Ordering: enriched static schemas first (original static order preserved),
    then discovered-only schemas appended in their original discovered order.

    Duplicates within *discovered* (same ``server`` + ``tool``): first
    occurrence wins; remaining are silently ignored.

    Parameters
    ----------
    static:
        Existing static schemas, e.g. from ``MCPSchemaStore.schemas``.
        May be empty.
    discovered:
        Schemas from ``discover_stdio_tools``; classification is always
        ``"unknown"``.  May be empty.

    Returns
    -------
    tuple[MCPToolSchema, ...]
        Merged schema tuple.  Never mutates inputs.
    """
    # Index discovered by (server, tool); first occurrence wins on duplicates.
    disc_index: dict[tuple[str, str], MCPToolSchema] = {}
    disc_order: list[tuple[str, str]] = []
    for d in discovered:
        key = (d.server, d.tool)
        if key not in disc_index:
            disc_index[key] = d
            disc_order.append(key)

    result: list[MCPToolSchema] = []
    matched_keys: set[tuple[str, str]] = set()

    for s in static:
        key = (s.server, s.tool)
        matched_keys.add(key)
        d = disc_index.get(key)
        if d is None:
            result.append(s)
        else:
            # Static wins on classification; fill description/args from discovered only if absent.
            description = s.description if s.description else d.description
            args = s.args if s.args else d.args
            if description == s.description and args == s.args:
                result.append(s)
            else:
                result.append(
                    MCPToolSchema(
                        server=s.server,
                        tool=s.tool,
                        classification=s.classification,
                        description=description,
                        args=args,
                        arg_schemas=s.arg_schemas,
                    )
                )

    # Append discovered-only schemas (no static counterpart) in discovery order.
    for key in disc_order:
        if key not in matched_keys:
            result.append(disc_index[key])

    return tuple(result)
