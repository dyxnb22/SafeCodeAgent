"""Repeatable demo workflow definitions and seed project materialization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DemoWorkflow:
    """One repeatable demo workflow with deterministic seed files."""

    id: str
    title: str
    category: str
    task: str
    description: str
    files: dict[str, str]
    commands: tuple[str, ...]
    expected_files: tuple[str, ...]
    acceptance: tuple[str, ...]


class DemoWorkflowSuite:
    """Materialize and inspect the built-in demo workflows."""

    def __init__(self, workflows: list[DemoWorkflow] | None = None) -> None:
        self.workflows = workflows or default_demo_workflows()

    def list(self) -> list[DemoWorkflow]:
        """Return workflows in deterministic order."""
        return list(self.workflows)

    def get(self, workflow_id: str) -> DemoWorkflow:
        """Return one workflow by id."""
        for workflow in self.workflows:
            if workflow.id == workflow_id:
                return workflow
        raise KeyError(f"Unknown demo workflow: {workflow_id}")

    def materialize(self, workflow_id: str, destination: Path, force: bool = False) -> Path:
        """Write a workflow seed project under ``destination/<workflow_id>``."""
        workflow = self.get(workflow_id)
        project_root = destination / workflow.id
        if project_root.exists() and any(project_root.iterdir()) and not force:
            raise FileExistsError(f"Demo workflow already exists: {project_root}")

        project_root.mkdir(parents=True, exist_ok=True)
        for relative_path, content in workflow.files.items():
            target = (project_root / relative_path).resolve()
            if not _inside_directory(target, project_root.resolve()):
                raise PermissionError(f"Demo file escapes workflow root: {relative_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return project_root


def default_demo_workflows() -> list[DemoWorkflow]:
    """Return the built-in v2.0.4 demo workflow suite."""
    return [
        DemoWorkflow(
            id="fastapi-health-endpoint",
            title="FastAPI health endpoint",
            category="fastapi",
            task="Add a /health endpoint that returns {'status': 'ok'}.",
            description="Small FastAPI service change with an app file and test target.",
            files={
                "pyproject.toml": _FASTAPI_PYPROJECT,
                "app/__init__.py": '"""FastAPI demo app."""\n',
                "app/main.py": _FASTAPI_MAIN,
                "tests/test_health.py": _FASTAPI_TEST,
                ".sac/config.toml": _PYTEST_CONFIG,
            },
            commands=("sac edit", "sac apply", "sac test run --yes"),
            expected_files=("app/main.py", "tests/test_health.py"),
            acceptance=("app/main.py contains @app.get(\"/health\")", "pytest tests pass"),
        ),
        DemoWorkflow(
            id="cli-version-flag",
            title="CLI version flag",
            category="cli",
            task="Add a --version flag to the demo CLI.",
            description="Small argparse CLI change with a focused command-line test.",
            files={
                "pyproject.toml": _CLI_PYPROJECT,
                "src/todo_cli/__init__.py": '__version__ = "0.1.0"\n',
                "src/todo_cli/cli.py": _CLI_MAIN,
                "tests/test_cli.py": _CLI_TEST,
                ".sac/config.toml": _PYTEST_CONFIG,
            },
            commands=("sac edit", "sac apply", "sac test run --yes"),
            expected_files=("src/todo_cli/cli.py", "tests/test_cli.py"),
            acceptance=("python -m todo_cli.cli --version prints a version", "pytest tests pass"),
        ),
        DemoWorkflow(
            id="docs-safety-note",
            title="Docs-only safety note",
            category="docs",
            task="Document how to review a SafeCode patch before applying it.",
            description="Documentation-only edit that should not require app tests.",
            files={
                "README.md": _DOCS_README,
                "docs/usage.md": _DOCS_USAGE,
                ".sac/config.toml": _DOCS_CONFIG,
            },
            commands=("sac edit", "sac apply", "sac history"),
            expected_files=("docs/usage.md",),
            acceptance=("docs/usage.md explains patch review before apply", "history shows patch events"),
        ),
        DemoWorkflow(
            id="failing-test-repair",
            title="Failing test repair",
            category="failing-test",
            task="Fix the calculator add function so the existing failing test passes.",
            description="Bug repair workflow that starts with one intentionally failing pytest.",
            files={
                "pyproject.toml": _CALC_PYPROJECT,
                "src/calculator.py": _CALC_SOURCE,
                "tests/test_calculator.py": _CALC_TEST,
                ".sac/config.toml": _PYTEST_CONFIG,
            },
            commands=("sac test run --yes", "sac edit", "sac apply", "sac test run --yes"),
            expected_files=("src/calculator.py", "tests/test_calculator.py"),
            acceptance=("initial pytest fails", "pytest passes after fixing src/calculator.py"),
        ),
    ]


def _inside_directory(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


_PYTEST_CONFIG = """[shell]
allowed_commands = ["pytest", "python"]
require_confirm_for_medium = false
"""

_DOCS_CONFIG = """[shell]
allowed_commands = ["git", "ls", "pwd", "echo"]
"""

_FASTAPI_PYPROJECT = """[project]
name = "safecode-fastapi-workflow"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi", "pytest"]
"""

_FASTAPI_MAIN = '''"""FastAPI demo target for SafeCode Agent."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root() -> dict[str, str]:
    """Return a tiny demo response."""
    return {"message": "hello from fastapi demo"}
'''

_FASTAPI_TEST = '''from app.main import app


def test_health_route_is_registered():
    paths = {route.path for route in app.routes}

    assert "/health" in paths
'''

_CLI_PYPROJECT = """[project]
name = "todo-cli-workflow"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pytest"]
"""

_CLI_MAIN = '''"""Tiny argparse demo CLI."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("item", nargs="?", default="write tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"next: {args.item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_CLI_TEST = '''import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from todo_cli.cli import main


def test_version_flag(capsys):
    assert main(["--version"]) == 0

    captured = capsys.readouterr()
    assert "todo" in captured.out.lower()
'''

_DOCS_README = """# Docs Workflow Demo

This seed project is intentionally documentation-only.
"""

_DOCS_USAGE = """# Usage

Run `sac edit` to create a pending patch, then inspect the diff before applying it.
"""

_CALC_PYPROJECT = """[project]
name = "calculator-workflow"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pytest"]
"""

_CALC_SOURCE = '''"""Tiny calculator with an intentional bug."""


def add(left: int, right: int) -> int:
    """Return the sum of two integers."""
    return left - right + 0
'''

_CALC_TEST = '''import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from calculator import add


def test_adds_two_numbers():
    assert add(2, 3) == 5
'''
