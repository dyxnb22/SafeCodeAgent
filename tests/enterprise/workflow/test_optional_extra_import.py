"""Optional enterprise extra must not require langgraph by default."""

import tomllib
from pathlib import Path


def test_default_install_does_not_require_langgraph_in_core_dependencies():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    core = pyproject.get("project", {}).get("dependencies", [])
    assert not any("langgraph" in dep for dep in core)
    extras = pyproject.get("project", {}).get("optional-dependencies", {})
    assert "enterprise" in extras
    assert any("langgraph" in dep for dep in extras["enterprise"])
