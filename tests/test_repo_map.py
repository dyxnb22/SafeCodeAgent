"""Repo map tests for v2.1.0."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.index.repo_map import RepoMapBuilder

runner = CliRunner()


def _write_demo_project(root: Path) -> None:
    (root / "src" / "demo").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        """[project]
name = "repo-map-demo"
version = "0.1.0"
dependencies = ["pytest"]

[project.scripts]
demo = "demo.cli:main"
""",
        encoding="utf-8",
    )
    (root / "src" / "demo" / "cli.py").write_text(
        '''"""Demo CLI."""

import argparse
from pathlib import Path


class DemoApp:
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args([])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )
    (root / "tests" / "test_cli.py").write_text(
        """from demo.cli import main


def test_main():
    assert main() == 0
""",
        encoding="utf-8",
    )


def test_repo_map_contains_files_symbols_imports_tests_commands_and_entrypoints(tmp_path: Path) -> None:
    _write_demo_project(tmp_path)

    repo_map = RepoMapBuilder(tmp_path).build()

    assert {item.path for item in repo_map.files} >= {
        "pyproject.toml",
        "src/demo/cli.py",
        "tests/test_cli.py",
    }
    assert {(item.kind, item.name, item.path) for item in repo_map.symbols} >= {
        ("class", "DemoApp", "src/demo/cli.py"),
        ("function", "main", "src/demo/cli.py"),
        ("function", "test_main", "tests/test_cli.py"),
    }
    assert {(item.path, item.module) for item in repo_map.imports} >= {
        ("src/demo/cli.py", "argparse"),
        ("src/demo/cli.py", "pathlib"),
        ("tests/test_cli.py", "demo.cli"),
    }
    assert [item.path for item in repo_map.tests] == ["tests/test_cli.py"]
    assert [item.command for item in repo_map.commands] == ["pytest -q"]
    assert {(item.kind, item.name, item.target) for item in repo_map.entrypoints} >= {
        ("project-script", "demo", "demo.cli:main"),
        ("python-main", "cli", "src/demo/cli.py"),
    }


def test_repo_map_json_is_stable_and_serializable(tmp_path: Path) -> None:
    _write_demo_project(tmp_path)

    data = json.loads(RepoMapBuilder(tmp_path).build().to_json())

    assert sorted(data) == ["commands", "entrypoints", "files", "imports", "symbols", "tests"]
    assert data["entrypoints"][0]["kind"] == "project-script"


def test_cli_index_map_renders_summary_and_json(tmp_path: Path, monkeypatch) -> None:
    _write_demo_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    summary = runner.invoke(app, ["index", "map"])
    json_result = runner.invoke(app, ["index", "map", "--json"])

    assert summary.exit_code == 0
    assert "SafeCode Repo Map" in summary.stdout
    assert "Entrypoints" in summary.stdout
    assert "Detected Commands" in summary.stdout
    assert json_result.exit_code == 0
    assert '"entrypoints"' in json_result.stdout
    assert '"pytest -q"' in json_result.stdout
