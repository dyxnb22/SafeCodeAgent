"""Repository map builder for lightweight code intelligence."""

from __future__ import annotations

import ast
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from safecode.index.files import FileIndexer, IndexedFile
from safecode.index.python_symbols import PythonSymbol, PythonSymbolIndexer
from safecode.project.test_detector import ProjectTestDetector, TestCommandCandidate


@dataclass(frozen=True)
class PythonImport:
    """One import found in a Python file."""

    path: str
    module: str
    line: int


@dataclass(frozen=True)
class IndexedTest:
    """One likely test file."""

    path: str
    framework: str
    reason: str


@dataclass(frozen=True)
class EntryPoint:
    """One detected project entrypoint."""

    name: str
    kind: str
    target: str
    path: str
    line: int | None = None


@dataclass(frozen=True)
class RepoMap:
    """A compact map of files, symbols, imports, tests, commands, and entrypoints."""

    files: list[IndexedFile]
    symbols: list[PythonSymbol]
    imports: list[PythonImport]
    tests: list[IndexedTest]
    commands: list[TestCommandCandidate]
    entrypoints: list[EntryPoint]

    def to_dict(self) -> dict:
        """Return JSON-serializable map data."""
        return {
            "files": [asdict(item) for item in self.files],
            "symbols": [asdict(item) for item in self.symbols],
            "imports": [asdict(item) for item in self.imports],
            "tests": [asdict(item) for item in self.tests],
            "commands": [asdict(item) for item in self.commands],
            "entrypoints": [asdict(item) for item in self.entrypoints],
        }

    def to_json(self) -> str:
        """Render the map as stable JSON."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


class RepoMapBuilder:
    """Build a deterministic repository map from safe indexed files."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def build(self) -> RepoMap:
        """Build the repository map."""
        files = FileIndexer(self.project_root).index()
        symbols = PythonSymbolIndexer(self.project_root).index()
        return RepoMap(
            files=files,
            symbols=symbols,
            imports=self._index_imports(files),
            tests=self._index_tests(files),
            commands=ProjectTestDetector(self.project_root).detect(),
            entrypoints=self._index_entrypoints(files),
        )

    def _index_imports(self, files: list[IndexedFile]) -> list[PythonImport]:
        imports: list[PythonImport] = []
        for indexed_file in files:
            if indexed_file.suffix != ".py":
                continue
            tree = self._parse_python(indexed_file.path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(PythonImport(indexed_file.path, alias.name, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    module = "." * node.level + (node.module or "")
                    imports.append(PythonImport(indexed_file.path, module, node.lineno))
        return imports

    def _index_tests(self, files: list[IndexedFile]) -> list[IndexedTest]:
        tests: list[IndexedTest] = []
        for indexed_file in files:
            path = Path(indexed_file.path)
            if indexed_file.suffix != ".py":
                continue
            if path.name.startswith("test_") or path.name.endswith("_test.py") or "tests" in path.parts:
                tests.append(IndexedTest(indexed_file.path, "pytest", "Python test path convention."))
        return tests

    def _index_entrypoints(self, files: list[IndexedFile]) -> list[EntryPoint]:
        entrypoints = self._pyproject_entrypoints()
        for indexed_file in files:
            if indexed_file.suffix != ".py":
                continue
            tree = self._parse_python(indexed_file.path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if _is_main_guard(node):
                    entrypoints.append(
                        EntryPoint(
                            name=Path(indexed_file.path).stem,
                            kind="python-main",
                            target=indexed_file.path,
                            path=indexed_file.path,
                            line=node.lineno,
                        )
                    )
        return entrypoints

    def _pyproject_entrypoints(self) -> list[EntryPoint]:
        pyproject = self.project_root / "pyproject.toml"
        if not pyproject.exists():
            return []
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return []
        scripts = data.get("project", {}).get("scripts", {})
        if not isinstance(scripts, dict):
            return []
        return [
            EntryPoint(name=name, kind="project-script", target=str(target), path="pyproject.toml")
            for name, target in sorted(scripts.items())
            if isinstance(target, str)
        ]

    def _parse_python(self, relative_path: str) -> ast.AST | None:
        path = self.project_root / relative_path
        try:
            return ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return None


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if not isinstance(test.left, ast.Name) or test.left.id != "__name__":
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    if len(test.comparators) != 1:
        return False
    comparator = test.comparators[0]
    return isinstance(comparator, ast.Constant) and comparator.value == "__main__"
