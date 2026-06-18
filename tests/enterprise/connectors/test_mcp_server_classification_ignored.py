"""MCP server classification is ignored for decisions."""

from safecode.enterprise.connectors.mcp_adapter import classify_discovered_tool
from safecode.enterprise.connectors.mcp_allowlist import MCPAllowlist, MCPAllowlistEntry
from safecode.enterprise.tools.registry import ApprovalTier, ToolCategory
from safecode.mcp.discovery import MCPTool


def test_server_claimed_category_is_not_used_for_decision():
    allowlist = MCPAllowlist(
        tools={
            "srv:tool": MCPAllowlistEntry(
                category=ToolCategory.read_local,
                approval_tier=ApprovalTier.CONFIRM,
                server_claimed_category="admin",
            )
        }
    )
    item = MCPTool(server="srv", name="srv.tool", risk="admin")
    assert classify_discovered_tool(item, allowlist) == ApprovalTier.CONFIRM
