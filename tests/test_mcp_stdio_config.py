"""Tests for v3.3.1: MCP stdio server config argv validation.

Covers: valid argv, missing server, missing stdio argv, empty argv,
shell-string rejection, non-list rejection, non-string item rejection,
and sanitized error text.

No subprocess execution; no call_stdio invocation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.mcp.config import (
    MCPConfigStore,
    MCPServerConfig,
    StdioArgvError,
    resolve_stdio_argv,
    validate_stdio_argv,
)


# ── validate_stdio_argv ───────────────────────────────────────────────────────


class TestValidateStdioArgv:
    def test_valid_single_item(self):
        result = validate_stdio_argv(["my-server"])
        assert result == ("my-server",)

    def test_valid_multiple_items(self):
        result = validate_stdio_argv(["python", "-m", "my_mcp_server"])
        assert result == ("python", "-m", "my_mcp_server")

    def test_returns_tuple(self):
        result = validate_stdio_argv(["a", "b"])
        assert isinstance(result, tuple)

    def test_all_string_items_accepted(self):
        result = validate_stdio_argv(["cmd", "--flag", "value"])
        assert len(result) == 3

    def test_empty_list_rejected(self):
        with pytest.raises(StdioArgvError, match="non-empty"):
            validate_stdio_argv([])

    def test_shell_string_rejected(self):
        with pytest.raises(StdioArgvError, match="shell string"):
            validate_stdio_argv("my-server --flag")

    def test_non_list_int_rejected(self):
        with pytest.raises(StdioArgvError, match="list"):
            validate_stdio_argv(42)

    def test_non_list_none_rejected(self):
        with pytest.raises(StdioArgvError, match="list"):
            validate_stdio_argv(None)

    def test_non_list_dict_rejected(self):
        with pytest.raises(StdioArgvError, match="list"):
            validate_stdio_argv({"cmd": "server"})

    def test_non_string_item_int_rejected(self):
        with pytest.raises(StdioArgvError, match="not a string"):
            validate_stdio_argv(["server", 123])

    def test_non_string_item_none_rejected(self):
        with pytest.raises(StdioArgvError, match="not a string"):
            validate_stdio_argv(["server", None])

    def test_non_string_item_list_rejected(self):
        with pytest.raises(StdioArgvError, match="not a string"):
            validate_stdio_argv(["server", ["nested"]])

    def test_non_string_item_reports_index(self):
        with pytest.raises(StdioArgvError, match="index 2"):
            validate_stdio_argv(["a", "b", 99])

    def test_error_does_not_include_item_value(self):
        secret_value = "sk-secret-token-9999"
        with pytest.raises(StdioArgvError) as exc_info:
            validate_stdio_argv(["server", secret_value, 42])
        assert secret_value not in str(exc_info.value)

    def test_shell_string_error_does_not_include_content(self):
        shell_string = "secret-server --token sk-abc123"
        with pytest.raises(StdioArgvError) as exc_info:
            validate_stdio_argv(shell_string)
        assert "sk-abc123" not in str(exc_info.value)


# ── resolve_stdio_argv ────────────────────────────────────────────────────────


class TestResolveStdioArgv:
    def _make_servers(self, *configs: MCPServerConfig) -> list[MCPServerConfig]:
        return list(configs)

    def test_valid_server_returns_argv(self):
        servers = self._make_servers(
            MCPServerConfig(name="myserver", command="", argv=("python", "-m", "srv"))
        )
        result = resolve_stdio_argv(servers, "myserver")
        assert result == ["python", "-m", "srv"]

    def test_returns_list(self):
        servers = self._make_servers(
            MCPServerConfig(name="s", command="", argv=("cmd",))
        )
        result = resolve_stdio_argv(servers, "s")
        assert isinstance(result, list)

    def test_multiple_servers_resolves_correct_one(self):
        servers = self._make_servers(
            MCPServerConfig(name="srv-a", command="", argv=("a-cmd",)),
            MCPServerConfig(name="srv-b", command="", argv=("b-cmd",)),
        )
        assert resolve_stdio_argv(servers, "srv-a") == ["a-cmd"]
        assert resolve_stdio_argv(servers, "srv-b") == ["b-cmd"]

    def test_missing_server_raises(self):
        servers = self._make_servers(
            MCPServerConfig(name="present", command="", argv=("cmd",))
        )
        with pytest.raises(StdioArgvError):
            resolve_stdio_argv(servers, "absent")

    def test_empty_servers_list_raises(self):
        with pytest.raises(StdioArgvError):
            resolve_stdio_argv([], "any-server")

    def test_server_without_argv_raises(self):
        servers = self._make_servers(
            MCPServerConfig(name="cmd-server", command="my-cmd", argv=None)
        )
        with pytest.raises(StdioArgvError, match="no stdio argv"):
            resolve_stdio_argv(servers, "cmd-server")

    def test_missing_server_error_has_server_name(self):
        with pytest.raises(StdioArgvError, match="not-a-server"):
            resolve_stdio_argv([], "not-a-server")

    def test_no_argv_error_has_server_name(self):
        servers = self._make_servers(
            MCPServerConfig(name="oldstyle", command="cmd", argv=None)
        )
        with pytest.raises(StdioArgvError, match="oldstyle"):
            resolve_stdio_argv(servers, "oldstyle")

    def test_error_text_does_not_contain_argv_values(self):
        # If resolve fails, error must not include the argv of other servers.
        secret_argv = ("secret-binary", "--token", "sk-secret-99")
        servers = self._make_servers(
            MCPServerConfig(name="other", command="", argv=secret_argv)
        )
        with pytest.raises(StdioArgvError) as exc_info:
            resolve_stdio_argv(servers, "missing-server")
        assert "sk-secret-99" not in str(exc_info.value)

    def test_disabled_server_still_resolves(self):
        # enabled flag does not affect argv resolution (caller decides whether to use).
        servers = self._make_servers(
            MCPServerConfig(name="srv", command="", enabled=False, argv=("cmd",))
        )
        result = resolve_stdio_argv(servers, "srv")
        assert result == ["cmd"]


# ── MCPServerConfig dataclass ─────────────────────────────────────────────────


class TestMCPServerConfigArgv:
    def test_argv_defaults_to_none(self):
        cfg = MCPServerConfig(name="s", command="cmd")
        assert cfg.argv is None

    def test_argv_stored_as_tuple(self):
        cfg = MCPServerConfig(name="s", command="", argv=("a", "b"))
        assert cfg.argv == ("a", "b")

    def test_is_frozen(self):
        cfg = MCPServerConfig(name="s", command="cmd", argv=("x",))
        with pytest.raises(Exception):
            cfg.argv = ("y",)  # type: ignore[misc]

    def test_existing_fields_unaffected(self):
        cfg = MCPServerConfig(name="srv", command="old-cmd", enabled=False)
        assert cfg.name == "srv"
        assert cfg.command == "old-cmd"
        assert cfg.enabled is False


# ── MCPConfigStore TOML parsing ───────────────────────────────────────────────


class TestMCPConfigStoreArgv:
    def _write_toml(self, tmp_path: Path, content: str) -> MCPConfigStore:
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        (sac_dir / "mcp.toml").write_text(content, encoding="utf-8")
        return MCPConfigStore(tmp_path)

    def test_parses_argv_from_toml(self, tmp_path):
        store = self._write_toml(
            tmp_path,
            '[servers.myserver]\nargv = ["python", "-m", "myserver"]\n',
        )
        servers = store.list_servers()
        assert len(servers) == 1
        assert servers[0].argv == ("python", "-m", "myserver")

    def test_server_without_argv_has_none(self, tmp_path):
        store = self._write_toml(
            tmp_path,
            '[servers.cmd-only]\ncommand = "mycmd"\n',
        )
        servers = store.list_servers()
        assert servers[0].argv is None

    def test_argv_and_command_coexist(self, tmp_path):
        store = self._write_toml(
            tmp_path,
            '[servers.both]\ncommand = "legacy"\nargv = ["new-cmd"]\n',
        )
        servers = store.list_servers()
        assert servers[0].command == "legacy"
        assert servers[0].argv == ("new-cmd",)

    def test_invalid_argv_non_list_raises(self, tmp_path):
        # TOML string value for argv is a shell string — must be rejected.
        store = self._write_toml(
            tmp_path,
            '[servers.bad]\nargv = "shell-string --flag"\n',
        )
        with pytest.raises(StdioArgvError):
            store.list_servers()

    def test_invalid_argv_empty_list_raises(self, tmp_path):
        store = self._write_toml(
            tmp_path,
            '[servers.bad]\nargv = []\n',
        )
        with pytest.raises(StdioArgvError):
            store.list_servers()

    def test_multiple_servers_mixed_argv(self, tmp_path):
        store = self._write_toml(
            tmp_path,
            '[servers.stdio-srv]\nargv = ["srv-bin"]\n'
            '[servers.cmd-srv]\ncommand = "old-cmd"\n',
        )
        servers = store.list_servers()
        by_name = {s.name: s for s in servers}
        assert by_name["stdio-srv"].argv == ("srv-bin",)
        assert by_name["cmd-srv"].argv is None

    def test_no_mcp_toml_returns_empty(self, tmp_path):
        store = MCPConfigStore(tmp_path)
        assert store.list_servers() == []

    def test_existing_command_field_still_works(self, tmp_path):
        store = self._write_toml(
            tmp_path,
            '[servers.legacy]\ncommand = "legacy-cmd"\nenabled = false\n',
        )
        servers = store.list_servers()
        assert servers[0].command == "legacy-cmd"
        assert servers[0].enabled is False
        assert servers[0].argv is None
