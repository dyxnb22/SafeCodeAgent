"""Read-only native tools: read_file, list_files, search_files, grep_files (v4.20.1+).

All four tools:
- Validate paths against the project root (refuse escapes).
- Skip sensitive, binary, and .sac/ / .git/ directories.
- Apply redact_secrets() to read_file output.
- Are auto-approved (no checkpoint needed).
- Audit as tool_call_read events.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.context.collector import SKIP_DIRS, SENSITIVE_PATTERNS, SENSITIVE_NAMES
from safecode.context.redactor import redact_secrets

_MAX_READ_LINES = 400
_MAX_SEARCH_RESULTS = 100
_MAX_LIST_FILES = 500

_SENSITIVE_NAMES_SET = frozenset(SENSITIVE_NAMES)


def _validate_path(project_root: Path, raw_path: str) -> tuple[Path, str | None]:
    """Return (resolved_absolute, error_msg). error_msg is None on success."""
    candidate = Path(raw_path)
    absolute = candidate if candidate.is_absolute() else project_root / candidate
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return project_root, f"Path {raw_path!r} is outside the project root."
    return resolved, None


def _is_safe_file(path: Path, project_root: Path) -> bool:
    """Return True if the file should be readable (not sensitive/binary/skipped)."""
    try:
        rel = path.relative_to(project_root.resolve())
    except ValueError:
        return False
    parts_lower = {p.lower() for p in rel.parts}
    if parts_lower & SKIP_DIRS:
        return False
    name = path.name.lower()
    if name in _SENSITIVE_NAMES_SET:
        return False
    rel_text = rel.as_posix().lower()
    if any(
        re.match(pat.replace("*", ".*").replace(".", r"\."), name)
        or re.match(pat.replace("*", ".*").replace(".", r"\."), rel_text)
        for pat in SENSITIVE_PATTERNS
    ):
        return False
    return True


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\0" in fh.read(1024)
    except OSError:
        return True


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _read_file_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    raw_path = inp.get("path", "")
    start_line: int = inp.get("start_line", 1) or 1
    end_line: int | None = inp.get("end_line", None)

    if not raw_path:
        return NativeToolResult(call_id=call_id, tool_name="read_file", status="error", error="Missing 'path' input.")

    resolved, err = _validate_path(project_root, raw_path)
    if err:
        return NativeToolResult(call_id=call_id, tool_name="read_file", status="blocked", error=err)

    if not resolved.is_file():
        return NativeToolResult(call_id=call_id, tool_name="read_file", status="error", error=f"File not found: {raw_path!r}")

    if not _is_safe_file(resolved, project_root):
        return NativeToolResult(call_id=call_id, tool_name="read_file", status="blocked", error=f"File {raw_path!r} is sensitive or excluded.")

    if _looks_binary(resolved):
        return NativeToolResult(call_id=call_id, tool_name="read_file", status="blocked", error=f"File {raw_path!r} appears to be binary.")

    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError as exc:
        return NativeToolResult(call_id=call_id, tool_name="read_file", status="error", error=f"Read error: {type(exc).__name__}")

    start_idx = max(0, start_line - 1)
    end_idx = len(lines) if end_line is None else min(end_line, start_idx + _MAX_READ_LINES)
    end_idx = min(end_idx, start_idx + _MAX_READ_LINES)
    selected = lines[start_idx:end_idx]

    output = redact_secrets("".join(selected))
    meta: dict[str, Any] = {"total_lines": len(lines), "returned_lines": len(selected)}
    if len(lines) > end_idx:
        meta["truncated"] = True
    return NativeToolResult(call_id=call_id, tool_name="read_file", output=output, metadata=meta)


def _list_files_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    import os
    project_root = Path(inp.get("_project_root", ".")).resolve()
    raw_path: str = inp.get("path", ".") or "."
    recursive: bool = inp.get("recursive", True)

    resolved, err = _validate_path(project_root, raw_path)
    if err:
        return NativeToolResult(call_id=call_id, tool_name="list_files", status="blocked", error=err)

    if not resolved.exists():
        return NativeToolResult(call_id=call_id, tool_name="list_files", status="error", error=f"Path not found: {raw_path!r}")

    entries: list[str] = []
    truncated = False

    if recursive:
        for root, dir_names, file_names in os.walk(resolved, followlinks=False):
            root_path = Path(root)
            dir_names[:] = sorted(
                d for d in dir_names
                if d not in SKIP_DIRS and not (root_path / d).is_symlink()
            )
            for fname in sorted(file_names):
                if len(entries) >= _MAX_LIST_FILES:
                    truncated = True
                    break
                full = root_path / fname
                try:
                    rel = full.relative_to(project_root)
                except ValueError:
                    continue
                if full.is_symlink():
                    continue
                entries.append(rel.as_posix())
            if truncated:
                break
    else:
        for child in sorted(resolved.iterdir()):
            if len(entries) >= _MAX_LIST_FILES:
                truncated = True
                break
            try:
                rel = child.relative_to(project_root)
            except ValueError:
                continue
            if child.is_symlink():
                continue
            marker = "/" if child.is_dir() else ""
            entries.append(rel.as_posix() + marker)

    output = "\n".join(entries)
    meta: dict[str, Any] = {"count": len(entries), "truncated": truncated}
    return NativeToolResult(call_id=call_id, tool_name="list_files", output=output, metadata=meta)


def _search_files_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    """Literal substring search (grep-like); uses index file map; no shell out."""
    import os
    project_root = Path(inp.get("_project_root", ".")).resolve()
    pattern: str = inp.get("pattern", "")
    raw_path: str = inp.get("path", ".") or "."
    include_glob: str = inp.get("include_glob", "") or ""

    if not pattern:
        return NativeToolResult(call_id=call_id, tool_name="search_files", status="error", error="Missing 'pattern' input.")

    search_root, err = _validate_path(project_root, raw_path)
    if err:
        return NativeToolResult(call_id=call_id, tool_name="search_files", status="blocked", error=err)

    from fnmatch import fnmatch

    results: list[dict[str, Any]] = []
    truncated = False

    for root, dir_names, file_names in os.walk(search_root, followlinks=False):
        root_path = Path(root)
        dir_names[:] = sorted(d for d in dir_names if d not in SKIP_DIRS)
        for fname in sorted(file_names):
            if len(results) >= _MAX_SEARCH_RESULTS:
                truncated = True
                break
            if include_glob and not fnmatch(fname, include_glob):
                continue
            full = root_path / fname
            if full.is_symlink() or not full.is_file():
                continue
            if not _is_safe_file(full, project_root):
                continue
            if _looks_binary(full):
                continue
            try:
                rel = full.relative_to(project_root).as_posix()
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern in line:
                    results.append({"file": rel, "line": lineno, "content": redact_secrets(line.rstrip())})
                    if len(results) >= _MAX_SEARCH_RESULTS:
                        truncated = True
                        break
        if truncated:
            break

    import json
    output = json.dumps(results, indent=None)
    return NativeToolResult(call_id=call_id, tool_name="search_files", output=output,
                            metadata={"count": len(results), "truncated": truncated})


def _grep_files_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    """Regex search; uses re module; no shell out."""
    import os, json
    project_root = Path(inp.get("_project_root", ".")).resolve()
    regex: str = inp.get("regex", "")
    raw_path: str = inp.get("path", ".") or "."
    case_insensitive: bool = inp.get("case_insensitive", False)

    if not regex:
        return NativeToolResult(call_id=call_id, tool_name="grep_files", status="error", error="Missing 'regex' input.")

    try:
        flags = re.IGNORECASE if case_insensitive else 0
        compiled = re.compile(regex, flags)
    except re.error as exc:
        return NativeToolResult(call_id=call_id, tool_name="grep_files", status="error", error=f"Invalid regex: {exc}")

    search_root, err = _validate_path(project_root, raw_path)
    if err:
        return NativeToolResult(call_id=call_id, tool_name="grep_files", status="blocked", error=err)

    results: list[dict[str, Any]] = []
    truncated = False

    for root, dir_names, file_names in os.walk(search_root, followlinks=False):
        root_path = Path(root)
        dir_names[:] = sorted(d for d in dir_names if d not in SKIP_DIRS)
        for fname in sorted(file_names):
            if len(results) >= _MAX_SEARCH_RESULTS:
                truncated = True
                break
            full = root_path / fname
            if full.is_symlink() or not full.is_file():
                continue
            if not _is_safe_file(full, project_root):
                continue
            if _looks_binary(full):
                continue
            try:
                rel = full.relative_to(project_root).as_posix()
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if compiled.search(line):
                    results.append({"file": rel, "line": lineno, "content": redact_secrets(line.rstrip())})
                    if len(results) >= _MAX_SEARCH_RESULTS:
                        truncated = True
                        break
        if truncated:
            break

    output = json.dumps(results, indent=None)
    return NativeToolResult(call_id=call_id, tool_name="grep_files", output=output,
                            metadata={"count": len(results), "truncated": truncated})


# ---------------------------------------------------------------------------
# search_symbol (v6.25) — ripgrep / grep + Python AST kind labeling
# ---------------------------------------------------------------------------

_SEARCH_SYMBOL_MAX = 50
_PY_KIND_PATTERNS = {
    "class": re.compile(r"^\s*class\s+\w"),
    "function": re.compile(r"^\s*(?:async\s+)?def\s+\w"),
    "import": re.compile(r"^\s*(?:import|from)\s+\w"),
}
_SYMBOL_DEF_PATTERNS = [
    (re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][\w]*)\b"), "function"),
    (re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][\w]*)\b"), "class"),
    (re.compile(r"\b(?:fn|func|function)\s+(?P<name>[A-Za-z_][\w]*)\b"), "function"),
    (re.compile(r"\btype\s+(?P<name>[A-Za-z_][\w]*)\b"), "class"),
    (re.compile(r"\b(?:const|var|let)\s+(?P<name>[A-Za-z_][\w]*)\b"), "variable"),
    (re.compile(r"^\s*(?P<name>[A-Za-z_][\w]*)\s*(?:=|:=|:)"), "variable"),
]


def _kind_from_line(line: str) -> str:
    for kind, pat in _PY_KIND_PATTERNS.items():
        if pat.match(line):
            return kind
    return "variable"


def _normalize_symbol_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _definition_match_from_line(line: str, requested: str, *, is_python: bool) -> tuple[str, str] | None:
    requested_norm = _normalize_symbol_name(requested)
    for pattern, fallback_kind in _SYMBOL_DEF_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        candidate = match.group("name")
        if candidate == requested or _normalize_symbol_name(candidate) == requested_norm:
            kind = _kind_from_line(line) if is_python else fallback_kind
            return candidate, kind
    return None


def _search_symbol_via_walk(project_root: Path, name: str, kind_filter: str | None,
                             file_filter: str | None) -> tuple[list[dict], bool]:
    """Pure-Python fallback symbol search using regex walk."""
    import os, json as _json  # noqa: F401

    results: list[dict] = []
    truncated = False

    search_root = project_root
    if file_filter:
        candidate = project_root / file_filter
        if candidate.is_file():
            search_root = candidate.parent

    for root, dir_names, file_names in os.walk(search_root, followlinks=False):
        root_path = Path(root)
        dir_names[:] = sorted(d for d in dir_names if d not in SKIP_DIRS)
        for fname in sorted(file_names):
            if len(results) >= _SEARCH_SYMBOL_MAX:
                truncated = True
                break
            full = root_path / fname
            if file_filter and full.name != Path(file_filter).name:
                continue
            if full.is_symlink() or not full.is_file():
                continue
            if not _is_safe_file(full, project_root):
                continue
            if _looks_binary(full):
                continue
            try:
                rel = full.relative_to(project_root).as_posix()
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            is_python = full.suffix == ".py"
            for lineno, line in enumerate(text.splitlines(), 1):
                matched = _definition_match_from_line(line, name, is_python=is_python)
                if matched is None:
                    continue
                _matched_name, k = matched
                if kind_filter and k != kind_filter:
                    continue
                results.append({
                    "file": rel,
                    "line": lineno,
                    "kind": k,
                    "snippet": redact_secrets(line.strip()[:160]),
                })
                if len(results) >= _SEARCH_SYMBOL_MAX:
                    truncated = True
                    break
        if truncated:
            break

    return results, truncated


def _search_symbol_via_ripgrep(project_root: Path, name: str, kind_filter: str | None,
                                file_filter: str | None) -> tuple[list[dict] | None, bool]:
    """Try ripgrep for faster multi-language search. Returns (None, False) if rg not available."""
    import subprocess, shutil, json as _json
    if not shutil.which("rg"):
        return None, False

    pattern = rf"\b(?:def|fn|func|function|class|type|const|var|let|async def)\s+{re.escape(name)}\b"
    args = ["rg", "--json", "--max-count=1", "-n", pattern]
    if file_filter:
        args += ["--", file_filter]
    else:
        args.append(str(project_root))

    try:
        proc = subprocess.run(
            args, cwd=project_root, capture_output=True, text=True, shell=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, False

    results: list[dict] = []
    truncated = False
    for raw_line in proc.stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            obj = _json.loads(raw_line)
        except Exception:
            continue
        if obj.get("type") != "match":
            continue
        data = obj.get("data", {})
        file_path = data.get("path", {}).get("text", "")
        lineno = data.get("line_number", 0)
        line_text = data.get("lines", {}).get("text", "").rstrip()
        try:
            rel = Path(file_path).relative_to(project_root).as_posix()
        except ValueError:
            rel = file_path
        is_python = rel.endswith(".py")
        k = _kind_from_line(line_text) if is_python else "symbol"
        if kind_filter and k != kind_filter:
            continue
        results.append({
            "file": rel,
            "line": lineno,
            "kind": k,
            "snippet": redact_secrets(line_text[:160]),
        })
        if len(results) >= _SEARCH_SYMBOL_MAX:
            truncated = True
            break

    return results, truncated


def _search_symbol_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    """Find where a symbol is defined across the project (v6.25)."""
    import json
    project_root = Path(inp.get("_project_root", ".")).resolve()
    name: str = inp.get("name", "").strip()
    kind_filter: str | None = inp.get("kind", None)  # function, class, variable, import
    file_filter: str | None = inp.get("file", None)  # restrict to specific file/path

    if not name:
        return NativeToolResult(call_id=call_id, tool_name="search_symbol", status="error",
                                error="Missing 'name'.")
    if len(name) < 2:
        return NativeToolResult(call_id=call_id, tool_name="search_symbol", status="error",
                                error="'name' must be at least 2 characters.")

    backend = "ripgrep"
    # Try ripgrep first (faster, multi-language).
    results, truncated = _search_symbol_via_ripgrep(project_root, name, kind_filter, file_filter)
    if results is None or not results:
        # Fallback to pure-Python walk. Also run it when ripgrep returns zero
        # results so snake_case queries can find camelCase/PascalCase symbols.
        backend = "walk" if results is None else "ripgrep+walk"
        results, truncated = _search_symbol_via_walk(project_root, name, kind_filter, file_filter)

    output = json.dumps(results, indent=None)
    return NativeToolResult(
        call_id=call_id,
        tool_name="search_symbol",
        output=output,
        metadata={"count": len(results), "truncated": truncated, "backend": backend},
    )


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

READ_FILE_SPEC = NativeToolSpec(
    name="read_file",
    description="Read a file inside the project root (up to 400 lines). Applies secret redaction.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project-relative file path."},
            "start_line": {"type": "integer", "description": "First line to read (1-indexed, default 1)."},
            "end_line": {"type": "integer", "description": "Last line to read (inclusive, default start+400)."},
        },
        "required": ["path"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
    experimental=False,  # Stable contract since v5.0.0
)

LIST_FILES_SPEC = NativeToolSpec(
    name="list_files",
    description="List files under a project path. Returns truncated:true when cap reached.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project-relative directory path (default: '.')."},
            "recursive": {"type": "boolean", "description": "Recurse into subdirectories (default: true)."},
        },
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
    experimental=False,  # Stable contract since v5.0.0
)

SEARCH_FILES_SPEC = NativeToolSpec(
    name="search_files",
    description="Literal substring search across project files. Returns [{file, line, content}] capped at 100.",
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Literal string to search for."},
            "path": {"type": "string", "description": "Directory to search under (default: '.')."},
            "include_glob": {"type": "string", "description": "Filename glob filter, e.g. '*.py'."},
        },
        "required": ["pattern"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
    experimental=False,  # Stable contract since v5.0.0
)

GREP_FILES_SPEC = NativeToolSpec(
    name="grep_files",
    description="Regex search across project files. Returns [{file, line, content}] capped at 100.",
    input_schema={
        "type": "object",
        "properties": {
            "regex": {"type": "string", "description": "Python regex pattern."},
            "path": {"type": "string", "description": "Directory to search under (default: '.')."},
            "case_insensitive": {"type": "boolean", "description": "Ignore case (default: false)."},
        },
        "required": ["regex"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
    experimental=False,  # Stable contract since v5.0.0
)


SEARCH_SYMBOL_SPEC = NativeToolSpec(
    name="search_symbol",
    description=(
        "Find where a symbol is defined before reading broad files. Use this for function, "
        "class, method, variable, constant, or type names mentioned in the task or errors. "
        "Matches snake_case and camelCase variants; uses ripgrep plus a built-in walk fallback. "
        "Returns [{file, line, kind, snippet}] capped at 50 results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Symbol name to search for."},
            "kind": {
                "type": "string",
                "description": "Optional kind filter: function, class, variable, import.",
                "enum": ["function", "class", "variable", "import", "symbol"],
            },
            "file": {"type": "string", "description": "Optional: restrict search to this file path."},
        },
        "required": ["name"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
    experimental=True,
)


def register_read_tools(dispatcher: NativeToolDispatcher, project_root: Path) -> None:
    """Register all read-only tools on a dispatcher, injecting project_root."""

    def make_handler(fn):
        def _handler(call_id: str, inp: dict) -> NativeToolResult:
            return fn(call_id, {"_project_root": str(project_root), **inp})
        return _handler

    dispatcher.register(READ_FILE_SPEC, make_handler(_read_file_handler))
    dispatcher.register(LIST_FILES_SPEC, make_handler(_list_files_handler))
    dispatcher.register(SEARCH_FILES_SPEC, make_handler(_search_files_handler))
    dispatcher.register(GREP_FILES_SPEC, make_handler(_grep_files_handler))
    dispatcher.register(SEARCH_SYMBOL_SPEC, make_handler(_search_symbol_handler))
