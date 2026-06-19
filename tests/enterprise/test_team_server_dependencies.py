"""Team Server optional extra boundary (D30)."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Accepted D30 package roots; ranges live in pyproject.toml.
D30_PACKAGE_ROOTS = (
    "fastapi",
    "uvicorn",
    "pydantic-settings",
    "psycopg",
    "httpx",
    "PyJWT",
)

TEAM_SERVER_MODULE_PREFIXES = (
    "fastapi",
    "uvicorn",
    "pydantic_settings",
    "psycopg",
    "httpx",
    "jwt",
)


def _load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_team_server_extra_declares_d30_dependencies() -> None:
    extras = _load_pyproject()["project"]["optional-dependencies"]
    assert "team-server" in extras
    declared = extras["team-server"]
    for package_root in D30_PACKAGE_ROOTS:
        assert any(package_root.lower() in dep.lower() for dep in declared), package_root
    assert any("pool" in dep for dep in declared), "psycopg pooling extra required"
    assert any("crypto" in dep for dep in declared), "PyJWT crypto extra required"


def test_base_and_enterprise_extras_exclude_team_server_dependencies() -> None:
    project = _load_pyproject()["project"]
    core = project["dependencies"]
    extras = project["optional-dependencies"]
    team_server = extras["team-server"]

    for dep in core:
        lowered = dep.lower()
        assert "fastapi" not in lowered
        assert "uvicorn" not in lowered
        assert "psycopg" not in lowered
        assert "pyjwt" not in lowered

    assert "enterprise" in extras
    enterprise = extras["enterprise"]
    assert enterprise == ["langgraph>=1.0.0,<2.0"]
    for dep in enterprise:
        lowered = dep.lower()
        assert "fastapi" not in lowered
        assert "psycopg" not in lowered

    for dep in team_server:
        lowered = dep.lower()
        assert "langgraph" not in lowered


def test_base_install_imports_without_team_server_dependencies() -> None:
    import safecode.cli  # noqa: F401
    import safecode.enterprise  # noqa: F401
    from safecode.enterprise import __about__

    assert __about__.__version__


def test_enterprise_import_does_not_eagerly_load_team_server_modules() -> None:
    before = set(sys.modules)
    importlib_result = __import__("safecode.enterprise", fromlist=["__about__"])
    __import__("safecode.enterprise.__about__")
    assert importlib_result is not None

    loaded = set(sys.modules) - before
    for prefix in TEAM_SERVER_MODULE_PREFIXES:
        eager = [name for name in loaded if name == prefix or name.startswith(f"{prefix}.")]
        assert not eager, f"eager import detected: {eager}"


@pytest.mark.subprocess
def test_uv_lock_check_passes() -> None:
    result = subprocess.run(
        ["uv", "lock", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.subprocess
def test_verify_package_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify-package.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
