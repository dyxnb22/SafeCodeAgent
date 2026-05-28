"""Python symbol indexing using the standard ast module."""

import ast
from dataclasses import dataclass
from pathlib import Path

from safecode.index.files import FileIndexer


@dataclass(frozen=True)
class PythonSymbol:
    """A class or function found in Python code."""

    name: str
    kind: str
    path: str
    line: int


class PythonSymbolIndexer:
    """Index Python classes and functions."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def index(self) -> list[PythonSymbol]:
        """Return symbols from safe Python files."""
        symbols: list[PythonSymbol] = []
        for indexed_file in FileIndexer(self.project_root).index():
            if indexed_file.suffix != ".py":
                continue
            path = self.project_root / indexed_file.path
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(PythonSymbol(node.name, "class", indexed_file.path, node.lineno))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(PythonSymbol(node.name, "function", indexed_file.path, node.lineno))
        return symbols
