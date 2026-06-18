"""MCP registration tests."""

from pathlib import Path

from safecode.enterprise.connectors.mcp_adapter import register_allowlisted_mcp_tools
from safecode.enterprise.connectors.mcp_allowlist import load_allowlist
from safecode.enterprise.tools.registry import ToolRegistry

_EXAMPLE = Path(__file__).resolve().parents[3] / "examples/enterprise/mcp_allowlist.yaml"


def test_mcp_registration_only_allowlisted_tools(tmp_path: Path):
    registry = ToolRegistry()
    allowlist = load_allowlist(_EXAMPLE)
    registered = register_allowlisted_mcp_tools(tmp_path, registry, allowlist)
    assert registered == []
    assert registry.lookup("mcp:unknown:tool") is None
