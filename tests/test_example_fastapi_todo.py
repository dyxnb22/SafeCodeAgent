from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "fastapi-todo"


def test_required_files_exist() -> None:
    required = [
        "pyproject.toml",
        ".sac/project_profile.json",
        "src/todo_api/__init__.py",
        "src/todo_api/app.py",
        "src/todo_api/store.py",
        "tests/test_app.py",
        "README.md",
    ]

    for relative in required:
        assert (EXAMPLE / relative).is_file(), relative


def test_project_profile_is_valid_and_has_deterministic_test_command() -> None:
    profile = json.loads((EXAMPLE / ".sac" / "project_profile.json").read_text(encoding="utf-8"))

    assert profile["name"] == "fastapi-todo"
    assert profile["stack"] == "python"
    assert profile["commands"]["test"] == "PYTHONPATH=src pytest -q"
    assert profile["commands"]["lint"] is None
    assert profile["commands"]["typecheck"] is None
    assert profile["commands"]["build"] is None


def test_example_package_is_not_safecode_package_code() -> None:
    example_package = (EXAMPLE / "src" / "todo_api").resolve()
    safecode_src = (ROOT / "src" / "safecode").resolve()

    assert safecode_src not in example_package.parents
    assert example_package.name == "todo_api"


def test_top_level_examples_extra_declares_runtime_test_dependencies() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "examples = [" in text
    for dependency in ("fastapi", "httpx", "pytest"):
        assert dependency in text


@pytest.mark.slow
@pytest.mark.subprocess
def test_baseline_endpoint_tests_pass_with_examples_dependencies() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=EXAMPLE,
        env={"PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout
