"""Discover tools from configured MCP servers.

This version intentionally does not launch arbitrary external processes. It
exposes configured servers as discoverable entries so permission and audit can
be developed before real MCP process management.
"""

from dataclasses import dataclass
from pathlib import Path

from safecode.mcp.config import MCPConfigStore


@dataclass(frozen=True)
class MCPTool:
    """A discovered MCP tool placeholder."""

    server: str
    name: str
    risk: str


class MCPDiscovery:
    """List available MCP tools from config."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def list_tools(self) -> list[MCPTool]:
        """Return placeholder tools for enabled servers."""
        tools: list[MCPTool] = []
        for server in MCPConfigStore(self.project_root).list_servers():
            if server.enabled:
                tools.append(MCPTool(server=server.name, name=f"{server.name}.list", risk="low"))
        return tools
