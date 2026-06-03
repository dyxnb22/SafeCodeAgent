"""MCP server configuration (v3.3.1: stdio argv support, experimental)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MCPServerConfig:
    """One configured MCP server."""

    name: str
    command: str
    enabled: bool = True
    # Experimental (v3.3.1): stdio argv; non-None means server supports stdio transport.
    # Must be non-empty and contain only str items when present.
    argv: tuple[str, ...] | None = None


class StdioArgvError(ValueError):
    """Raised when stdio argv resolution fails.

    Error text never contains caller-supplied params or secret values.
    """


def validate_stdio_argv(raw: object) -> tuple[str, ...]:
    """Validate a raw argv value from config and return a validated tuple.

    Accepts only a non-empty list of strings.  Rejects shell strings (a plain
    str), empty lists, non-list types, and lists containing non-string items.

    Parameters
    ----------
    raw:
        The raw value read from config (e.g., from TOML ``argv = [...]``).

    Returns
    -------
    tuple[str, ...]
        Validated, non-empty argv tuple.

    Raises
    ------
    StdioArgvError
        On any validation failure.  Error text never includes the raw value
        content to avoid leaking potential secrets embedded in argv.
    """
    if isinstance(raw, str):
        raise StdioArgvError("stdio argv must be a list, not a shell string")
    if not isinstance(raw, list):
        raise StdioArgvError("stdio argv must be a list")
    if len(raw) == 0:
        raise StdioArgvError("stdio argv must be non-empty")
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise StdioArgvError(f"stdio argv item at index {i} is not a string")
    return tuple(raw)


def resolve_stdio_argv(servers: list[MCPServerConfig], server_name: str) -> list[str]:
    """Return validated argv for a named stdio server.

    Fails closed on: missing server, server without stdio argv, empty argv,
    invalid argv type, or invalid argv item type.  Error text never contains
    the argv contents.

    Parameters
    ----------
    servers:
        List of configured servers (from ``MCPConfigStore.list_servers()``).
    server_name:
        Name of the server to resolve.

    Returns
    -------
    list[str]
        Validated, non-empty argv ready for subprocess use.

    Raises
    ------
    StdioArgvError
        On any failure.
    """
    for server in servers:
        if server.name == server_name:
            if server.argv is None:
                raise StdioArgvError(
                    f"Server '{server_name}' has no stdio argv configured"
                )
            # argv was already validated at parse time; re-validate defensively.
            if len(server.argv) == 0:
                raise StdioArgvError(f"Server '{server_name}' stdio argv is empty")
            return list(server.argv)
    raise StdioArgvError(f"MCP server not found: '{server_name}'")


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
        result: list[MCPServerConfig] = []
        for name, config in servers.items():
            argv: tuple[str, ...] | None = None
            raw_argv = config.get("argv")
            if raw_argv is not None:
                argv = validate_stdio_argv(raw_argv)
            result.append(
                MCPServerConfig(
                    name=name,
                    command=str(config.get("command", "")),
                    enabled=bool(config.get("enabled", True)),
                    argv=argv,
                )
            )
        return result
