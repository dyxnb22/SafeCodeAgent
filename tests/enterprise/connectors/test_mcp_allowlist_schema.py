"""MCP allowlist schema tests."""

from pathlib import Path

from safecode.enterprise.connectors.mcp_allowlist import MCPAllowlist, load_allowlist, lookup_allowlist
from safecode.enterprise.tools.registry import ApprovalTier

_EXAMPLE = Path(__file__).resolve().parents[3] / "examples/enterprise/mcp_allowlist.yaml"


def test_allowlist_loads_typed_entries():
    allowlist = load_allowlist(_EXAMPLE)
    entry = lookup_allowlist(allowlist, "internal-docs", "search")
    assert entry is not None
    assert entry.approval_tier == ApprovalTier.CONFIRM


def test_missing_allowlist_entry_defaults_to_block():
    allowlist = MCPAllowlist()
    assert lookup_allowlist(allowlist, "unknown", "tool") is None
