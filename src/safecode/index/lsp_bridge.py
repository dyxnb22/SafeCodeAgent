"""Semantic symbol analysis bridge (v6.9.0).

Provides two backends:

  JediBridge   — uses the ``jedi`` Python library for semantic find_references.
                 No subprocess; pure Python API. Optional dependency.

  PyrightBridge — runs ``pyright --outputjson`` for type-check diagnostics.
                  Used by the repair strategy to get precise error locations.
                  Requires pyright in PATH. Optional.

Both classes fail gracefully when the backend is unavailable: ``is_available()``
returns False and ``find_references()`` / ``get_diagnostics()`` return [].

Safety:
- JediBridge never executes user code (jedi uses AST analysis).
- PyrightBridge uses shell=False, timeout=15s, and fails silently.
- All file paths are validated against project_root before returning.
- Results are capped to avoid unbounded output.
"""

from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path
from typing import Any


_MAX_REFS = 200       # jedi reference result cap
_MAX_DIAG = 100       # pyright diagnostic result cap


# ---------------------------------------------------------------------------
# JediBridge
# ---------------------------------------------------------------------------


class JediBridge:
    """Semantic find_references via the jedi library."""

    @staticmethod
    def is_available() -> bool:
        try:
            import jedi  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def find_references(
        symbol: str,
        definition_file: str,
        definition_line: int,
        project_root: Path,
    ) -> list[dict[str, Any]]:
        """Return semantic references to *symbol* defined at *definition_file:definition_line*.

        Uses ``jedi.Script.get_references()`` which searches across the whole project.
        Results are filtered to stay inside *project_root*.

        Returns [] on any error (jedi unavailable, parse error, timeout).
        """
        if not JediBridge.is_available():
            return []
        try:
            import jedi

            abs_path = (project_root / definition_file).resolve()
            if not abs_path.is_file():
                return []

            # Jedi works best when given the project root so it can resolve imports.
            project = jedi.Project(path=str(project_root))
            script = jedi.Script(path=str(abs_path), project=project)

            # Find the column of the symbol on the definition line.
            source_lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if definition_line < 1 or definition_line > len(source_lines):
                return []
            line_text = source_lines[definition_line - 1]
            col = line_text.find(symbol)
            if col < 0:
                return []

            raw_refs = script.get_references(definition_line, col)
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        root = project_root.resolve()
        for ref in raw_refs[:_MAX_REFS]:
            try:
                ref_path = Path(str(ref.module_path)).resolve()
                rel = ref_path.relative_to(root).as_posix()
            except (ValueError, TypeError):
                continue
            line_no = ref.line or 0
            # Read a snippet from the file
            snippet = ""
            try:
                lines = ref_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if 0 < line_no <= len(lines):
                    snippet = lines[line_no - 1].strip()[:120]
            except Exception:
                pass
            results.append({"file": rel, "line": line_no, "snippet": snippet, "type": ref.type or ""})

        return results


# ---------------------------------------------------------------------------
# PyrightBridge
# ---------------------------------------------------------------------------


class PyrightBridge:
    """Run pyright for type diagnostics (used by repair strategies)."""

    @staticmethod
    def is_available() -> bool:
        return shutil.which("pyright") is not None

    @staticmethod
    def get_diagnostics(project_root: Path) -> list[dict[str, Any]]:
        """Run ``pyright --outputjson`` and return structured diagnostics.

        Each entry: ``{file, line, column, message, severity, rule}``.
        Returns [] when pyright is unavailable or fails.
        """
        if not PyrightBridge.is_available():
            return []
        try:
            result = subprocess.run(
                ["pyright", "--outputjson"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                shell=False,
                timeout=15,
            )
            data = json.loads(result.stdout)
        except Exception:
            return []

        diagnostics: list[dict[str, Any]] = []
        root = project_root.resolve()
        for diag in data.get("generalDiagnostics", [])[:_MAX_DIAG]:
            try:
                file_abs = Path(str(diag.get("file", ""))).resolve()
                rel = file_abs.relative_to(root).as_posix()
            except (ValueError, TypeError, OSError):
                rel = str(diag.get("file", ""))
            range_info = diag.get("range", {})
            start = range_info.get("start", {})
            diagnostics.append({
                "file": rel,
                "line": start.get("line", 0) + 1,   # pyright uses 0-based lines
                "column": start.get("character", 0),
                "message": diag.get("message", ""),
                "severity": diag.get("severity", "error"),
                "rule": diag.get("rule", ""),
            })
        return diagnostics
