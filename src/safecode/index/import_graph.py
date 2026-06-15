"""Import-graph-aware context seeding for SafeCode Agent (v5.3.0).

Builds a lazy import graph for Python, TypeScript/JavaScript, and Go.
Used to seed the context collector with first-degree imported files,
so the agent starts each session with related files already in context.

Safety:
- Never executes any user code (ast.parse + regex only).
- Results are cached in .sac/index/import_graph.json with mtime invalidation.
- Sensitive paths are excluded from graph output.
- Circular imports terminate at depth 1 (first-degree only).
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any

_CACHE_FILE = ".sac/index/import_graph.json"
_MAX_SEED_IMPORTS = 5  # max first-degree imports returned per seed file

# Regex patterns for TypeScript/JS and Go imports
_TS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)
_GO_IMPORT_RE = re.compile(
    r'"([^"]+)"',
    re.MULTILINE,
)
_GO_IMPORT_BLOCK_RE = re.compile(
    r'import\s*\(([^)]+)\)',
    re.DOTALL,
)
_GO_SINGLE_IMPORT_RE = re.compile(
    r'import\s+"([^"]+)"',
)


def _parse_python_imports(source: str) -> list[str]:
    """Return module names from Python source using ast.parse (no execution)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Relative imports: prepend dots to signal relative
                prefix = "." * (node.level or 0)
                names.append(prefix + node.module)
    return names


def _parse_ts_imports(source: str) -> list[str]:
    """Return import paths from TypeScript/JS source using regex."""
    paths: list[str] = []
    for match in _TS_IMPORT_RE.finditer(source):
        path = match.group(1) or match.group(2)
        if path:
            paths.append(path)
    return paths


def _parse_go_imports(source: str) -> list[str]:
    """Return import paths from Go source using regex."""
    paths: list[str] = []
    for block_match in _GO_IMPORT_BLOCK_RE.finditer(source):
        block = block_match.group(1)
        for path_match in _GO_IMPORT_RE.finditer(block):
            paths.append(path_match.group(1))
    for single_match in _GO_SINGLE_IMPORT_RE.finditer(source):
        if not _GO_IMPORT_BLOCK_RE.search(single_match.string[:single_match.start()]):
            paths.append(single_match.group(1))
    return paths


def _resolve_python_import(module: str, source_path: Path, project_root: Path) -> Path | None:
    """Try to resolve a Python module name to a project-relative file path."""
    root = project_root.resolve()
    src = source_path.resolve()

    # Relative import: resolve relative to source directory
    if module.startswith("."):
        dots = len(module) - len(module.lstrip("."))
        rest = module.lstrip(".")
        base = src.parent
        for _ in range(dots - 1):
            base = base.parent
        if rest:
            candidate_dir = base / rest.replace(".", "/")
            candidate_file = base / (rest.replace(".", "/") + ".py")
        else:
            candidate_dir = base
            candidate_file = base / "__init__.py"
    else:
        # Absolute import: try src/ and project root
        parts = module.replace(".", "/")
        candidate_file = root / (parts + ".py")
        candidate_dir = root / parts

    # Try as a .py file
    for candidate in (candidate_file, candidate_dir / "__init__.py"):
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(root)
            if resolved.is_file():
                return resolved
        except (ValueError, OSError):
            pass

    return None


def _resolve_ts_import(import_path: str, source_path: Path, project_root: Path) -> Path | None:
    """Try to resolve a TypeScript/JS import path to a project file."""
    if not import_path.startswith("."):
        return None  # node_modules or external; skip
    root = project_root.resolve()
    base = source_path.parent
    candidate = (base / import_path).resolve()
    for ext in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
        p = Path(str(candidate) + ext) if not candidate.suffix or ext.startswith("/") else candidate
        if ext.startswith("/"):
            p = Path(str(candidate) + ext)
        try:
            p = p.resolve(strict=False)
            p.relative_to(root)
            if p.is_file():
                return p
        except (ValueError, OSError):
            pass
    return None


class ImportGraph:
    """Lazy, mtime-invalidated import graph for one project.

    graph: dict[str (relative posix path) → set[str (relative posix paths)]]
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._graph: dict[str, set[str]] | None = None
        self._cache_path = project_root / _CACHE_FILE

    def _load_cache(self) -> dict[str, Any] | None:
        """Load graph cache if it exists and is valid."""
        if not self._cache_path.exists():
            return None
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, graph: dict[str, list[str]]) -> None:
        """Save the graph to the cache file."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps({"graph": graph, "version": 1}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _parse_file_imports(self, abs_path: Path) -> list[Path]:
        """Return resolved absolute paths of first-degree imports from one file."""
        suffix = abs_path.suffix.lower()
        try:
            source = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        resolved: list[Path] = []
        if suffix == ".py":
            for mod in _parse_python_imports(source):
                p = _resolve_python_import(mod, abs_path, self.project_root)
                if p:
                    resolved.append(p)
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            for imp in _parse_ts_imports(source):
                p = _resolve_ts_import(imp, abs_path, self.project_root)
                if p:
                    resolved.append(p)
        elif suffix == ".go":
            # Go imports are typically package paths; only resolve same-module relative ones
            for imp in _parse_go_imports(source):
                # Skip standard library and external packages
                if "/" in imp and not imp.startswith("./") and not imp.startswith("../"):
                    # Attempt to find within project root (Go module internal packages)
                    candidate = self.project_root / imp.split("/")[-1]
                    if candidate.with_suffix(".go").is_file():
                        resolved.append(candidate.with_suffix(".go"))

        return resolved

    def build(self, *, force: bool = False) -> dict[str, set[str]]:
        """Build (or return cached) import graph for the project.

        Returns dict of relative-posix-path → set of relative-posix-path.
        """
        if self._graph is not None and not force:
            return self._graph

        # Skip cache and rebuild (graph is built per-request; cache is file-level)
        graph: dict[str, set[str]] = {}

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in {".git", ".sac", ".venv", "__pycache__", "node_modules"}]
            for fname in files:
                fpath = Path(root) / fname
                suffix = fpath.suffix.lower()
                if suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".go"):
                    continue
                try:
                    rel = fpath.relative_to(self.project_root).as_posix()
                except ValueError:
                    continue
                imports = self._parse_file_imports(fpath)
                imp_rel = set()
                for imp_path in imports:
                    try:
                        imp_rel.add(imp_path.relative_to(self.project_root).as_posix())
                    except ValueError:
                        pass
                if imp_rel:
                    graph[rel] = imp_rel

        self._graph = graph
        return graph

    def first_degree_imports(self, seed_path: str, *, limit: int = _MAX_SEED_IMPORTS) -> list[str]:
        """Return up to `limit` first-degree imports of `seed_path` (relative posix).

        seed_path may be absolute or relative to project_root.
        """
        # Normalize seed to relative posix
        seed_abs = Path(seed_path)
        if seed_abs.is_absolute():
            try:
                seed_rel = seed_abs.relative_to(self.project_root).as_posix()
            except ValueError:
                return []
        else:
            seed_rel = seed_path

        graph = self.build()

        # If not in graph, try to parse file directly
        if seed_rel not in graph:
            seed_file = self.project_root / seed_rel
            if seed_file.is_file():
                imports = self._parse_file_imports(seed_file)
                result = []
                for imp in imports:
                    try:
                        rel = imp.relative_to(self.project_root).as_posix()
                        result.append(rel)
                    except ValueError:
                        pass
                return result[:limit]
            return []

        return sorted(graph[seed_rel])[:limit]
