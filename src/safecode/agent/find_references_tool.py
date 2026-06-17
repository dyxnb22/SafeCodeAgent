"""find_references native tool (v6.9.0).

Queries the Python symbol index + import graph to find where a symbol
(function or class) is referenced across the project.

Safety:
- Read-only, auto-approved (requires_approval=False), path-validated.
- Results capped at _MAX_RESULTS.
- Paths are project-root-relative.
- Never executes user code (AST + regex only, same as the underlying indexers).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec

_MAX_RESULTS = 100
_MAX_SNIPPET_CHARS = 120
_SKIP_DIRS = frozenset({
    ".git", ".sac", "__pycache__", ".mypy_cache", "node_modules", ".venv", "venv",
})

_TOOL_NAME = "find_references"


class AmbiguousSymbolError(ValueError):
    """Raised when a symbol has multiple definitions and no file hint was provided."""

    def __init__(self, symbol: str, definitions: list[tuple[str, int]]) -> None:
        self.symbol = symbol
        self.definitions = definitions
        choices = ", ".join(f"{path}:{line}" for path, line in definitions[:10])
        suffix = "" if len(definitions) <= 10 else f", ... ({len(definitions)} total)"
        super().__init__(
            f"Symbol {symbol!r} has multiple definitions. "
            f"Pass --file to choose one: {choices}{suffix}"
        )


_SPEC = NativeToolSpec(
    name=_TOOL_NAME,
    description=(
        "Find where a Python function or class is defined and referenced across the project. "
        "Returns file:line pairs with a code snippet. "
        "Use this before renaming a symbol or changing a function signature."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "The function or class name to search for.",
            },
            "file": {
                "type": "string",
                "description": "(Optional) Restrict definition lookup to this relative file path.",
            },
        },
        "required": ["symbol"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
)


# --------------------------------------------------------------------------- #
# Core logic
# --------------------------------------------------------------------------- #


def _safe_relative(path: Path, project_root: Path) -> str | None:
    try:
        return path.resolve(strict=False).relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None


def _iter_python_files(project_root: Path):
    for py_file in project_root.rglob("*.py"):
        parts = {p.lower() for p in py_file.parts}
        if parts & _SKIP_DIRS:
            continue
        rel = _safe_relative(py_file, project_root)
        if rel is None:
            continue
        yield py_file, rel


def find_references(symbol: str, project_root: Path, file: str | None = None) -> list[dict[str, Any]]:
    """Return up to _MAX_RESULTS call-site references to *symbol*.

    Strategy (v6.9.0 updated):
    1. Use PythonSymbolIndexer to locate the definition file(s) + line numbers.
    2. Try JediBridge for semantic references (precise, handles aliases/renames).
       If jedi is available AND finds results → return them directly.
    3. Fallback: ImportGraph reverse-index + regex grep.
    """
    from safecode.index.python_symbols import PythonSymbolIndexer
    from safecode.index.import_graph import ImportGraph
    from safecode.index.lsp_bridge import JediBridge

    if not symbol or not symbol.isidentifier():
        return []

    # --- 1: find definition file(s) + lines ---
    all_syms = PythonSymbolIndexer(project_root).index()
    definition_files: set[str] = set()
    definition_info: list[tuple[str, int]] = []   # (rel_path, line)
    for sym in all_syms:
        if sym.name == symbol:
            if file is None or sym.path == file:
                definition_files.add(sym.path)
                definition_info.append((sym.path, sym.line))

    if file is None and len(definition_info) > 1:
        raise AmbiguousSymbolError(symbol, definition_info)

    # --- 2: try jedi semantic search ---
    if JediBridge.is_available() and definition_info:
        def_file, def_line = definition_info[0]
        jedi_refs = JediBridge.find_references(symbol, def_file, def_line, project_root)
        if jedi_refs:
            return jedi_refs[:_MAX_RESULTS]

    # --- 3: fallback: ImportGraph + regex ---
    graph = ImportGraph(project_root).build()
    importing_files: set[str] = set()
    for importer, imported_set in graph.items():
        if imported_set & definition_files:
            importing_files.add(importer)

    search_files: set[str] = definition_files | importing_files
    if not search_files:
        search_files = {rel for _, rel in _iter_python_files(project_root)}

    # --- 3: grep for symbol ---
    pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")
    results: list[dict[str, Any]] = []

    for rel in sorted(search_files):
        if len(results) >= _MAX_RESULTS:
            break
        full_path = project_root / rel
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                results.append({
                    "file": rel,
                    "line": lineno,
                    "snippet": line.strip()[:_MAX_SNIPPET_CHARS],
                })
                if len(results) >= _MAX_RESULTS:
                    break

    return results


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #


def _handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", "."))
    symbol = str(inp.get("symbol", "")).strip()
    file_hint = inp.get("file")

    if not symbol:
        return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="error", error="symbol is required")
    if not symbol.isidentifier():
        return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="error",
                                error=f"Invalid symbol name: {symbol!r}")

    if file_hint is not None:
        file_hint = str(file_hint).strip()
        try:
            resolved = (project_root / file_hint).resolve(strict=False)
            resolved.relative_to(project_root.resolve())
        except ValueError:
            return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="blocked",
                                    error="file path is outside project root")

    try:
        refs = find_references(symbol, project_root, file=file_hint)
    except AmbiguousSymbolError as exc:
        return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="blocked", error=str(exc))
    except Exception as exc:
        return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="error",
                                error=f"find_references failed: {type(exc).__name__}: {exc}")

    if not refs:
        return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="success",
                                output=f"No references found for '{symbol}'.")

    lines = [f"References to '{symbol}' ({len(refs)} found):"]
    for ref in refs:
        lines.append(f"  {ref['file']}:{ref['line']}  {ref['snippet']}")
    return NativeToolResult(call_id=call_id, tool_name=_TOOL_NAME, status="success",
                            output="\n".join(lines))


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def register_find_references_tool(dispatcher: NativeToolDispatcher, project_root: Path) -> None:
    """Register find_references as a read-only native tool."""
    def _bound(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
        return _handler(call_id, {"_project_root": str(project_root), **inp})

    dispatcher.register(_SPEC, _bound)
