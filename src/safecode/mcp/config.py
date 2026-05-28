"""MCP server configuration."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MCPServerConfig:
    """One configured MCP server."""

    name: str
    command: str
    enabled: bool = True


class MCPConfigStore:
    """Read .sac/mcp.toml."""

    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".sac" / "mcp.toml"

    def list_servers(self) -> list[MCPServerConfig]:
        """Read configured MCP servers."""
        if not self.path.exists():
            return []
        data = tomllib.loads(self.path.read_text(encoding="utf-8"))
        servers = data.get("servers", {})
        return [
            MCPServerConfig(name=name, command=str(config.get("command", "")), enabled=bool(config.get("enabled", True)))
            for name, config in servers.items()
        ]
