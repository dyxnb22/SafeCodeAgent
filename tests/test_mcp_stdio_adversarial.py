"""v3.3.6 adversarial hardening tests for the MCP stdio experimental surface.

Covers security properties not explicitly tested in v3.3.1-v3.3.5:
1. Server-supplied "classification" field in JSON response is ignored.
2. sac mcp stdio-discover has no execution path to StdioReadOnlyAdapter.
3. --timeout flag propagates to discover_stdio_tools.
4. StdioReadOnlyAdapter gates on static classification after merge.
5. Shell string in TOML config fails at parse time, never reaches subprocess.
6. Discovered-only tools (unknown) are blocked by adapter even after merge.
7. Oversized response fails closed at discovery level.
8. Error text from discovery failure never contains server response content.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from typer.testing import CliRunner

from safecode.cli_mcp import mcp_app
from safecode.mcp.config import MCPConfigStore, MCPServerConfig, StdioArgvError
from safecode.mcp.discovery import StdioDiscoveryResult, _parse_tool_entry
from safecode.mcp.schema import MCPToolSchema, classify_with_schema, merge_discovered_schemas
from safecode.mcp.stdio_runner import StdioReadOnlyAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _static(tool: str, classification: str, server: str = "srv") -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification=classification)


def _disc(tool: str, server: str = "srv") -> MCPToolSchema:
    return MCPToolSchema(server=server, tool=tool, classification="unknown")


_runner = Runner = Runner = Runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Server-supplied "classification" field in JSON response is ignored
# ---------------------------------------------------------------------------


class TestParserIgnoresServerClassification:
    """_parse_tool_entry must never honour a "classification" field from the server."""

    def test_server_sends_read_classification_still_unknown(self) -> None:
        entry = {"name": "read_files", "classification": "read"}
        schema = _parse_tool_entry(entry, "srv")
        assert schema is not None
        assert schema.classification == "unknown"

    def test_server_sends_write_classification_still_unknown(self) -> None:
        entry = {"name": "delete_all", "classification": "write"}
        schema = _parse_tool_entry(entry, "srv")
        assert schema is not None
        assert schema.classification == "unknown"

    def test_server_sends_arbitrary_classification_still_unknown(self) -> None:
        entry = {"name": "do_thing", "classification": "admin"}
        schema = _parse_tool_entry(entry, "srv")
        assert schema is not None
        assert schema.classification == "unknown"

    def test_server_sends_classification_along_with_description(self) -> None:
        entry = {"name": "list_dir", "classification": "read", "description": "Lists dir"}
        schema = _parse_tool_entry(entry, "srv")
        assert schema is not None
        assert schema.classification == "unknown"
        assert schema.description == "Lists dir"

    def test_server_sends_classification_with_input_schema(self) -> None:
        entry = {
            "name": "fetch_url",
            "classification": "read",
            "inputSchema": {"properties": {"url": {}}},
        }
        schema = _parse_tool_entry(entry, "srv")
        assert schema is not None
        assert schema.classification == "unknown"
        assert "url" in schema.args

    def test_no_classification_field_still_unknown(self) -> None:
        entry = {"name": "grep"}
        schema = _parse_tool_entry(entry, "srv")
        assert schema is not None
        assert schema.classification == "unknown"


# ---------------------------------------------------------------------------
# 2. CLI stdio-discover has no execution path to StdioReadOnlyAdapter
# ---------------------------------------------------------------------------


class TestDiscoveryCLIHasNoAdapterCall:
    """sac mcp stdio-discover must never invoke StdioReadOnlyAdapter."""

    def test_adapter_not_called_on_successful_discovery(self) -> None:
        disc_result = StdioDiscoveryResult(
            success=True,
            schemas=(_disc("read_file"),),
            server_name="srv",
        )
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", return_value=disc_result),
            patch("safecode.mcp.stdio_runner.StdioReadOnlyAdapter") as mock_adapter,
        ):
            mock_store.return_value.list_servers.return_value = [
                MCPServerConfig("srv", "run-srv", argv=("python", "srv.py"))
            ]
            _runner.invoke(mcp_app, ["stdio-discover", "srv"])
        mock_adapter.assert_not_called()

    def test_adapter_not_called_on_failed_discovery(self) -> None:
        disc_result = StdioDiscoveryResult(
            success=False, error="timeout", server_name="srv"
        )
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", return_value=disc_result),
            patch("safecode.mcp.stdio_runner.StdioReadOnlyAdapter") as mock_adapter,
        ):
            mock_store.return_value.list_servers.return_value = [
                MCPServerConfig("srv", "run-srv", argv=("python", "srv.py"))
            ]
            _runner.invoke(mcp_app, ["stdio-discover", "srv"])
        mock_adapter.assert_not_called()

    def test_stdio_discover_does_not_import_adapter_in_cli_module(self) -> None:
        import safecode.cli_mcp as cli_module
        assert not hasattr(cli_module, "StdioReadOnlyAdapter")

    def test_stdio_discover_help_has_no_call_option(self) -> None:
        result = _runner.invoke(mcp_app, ["stdio-discover", "--help"])
        assert "--call" not in result.output
        assert "--execute" not in result.output


# ---------------------------------------------------------------------------
# 3. --timeout flag propagates correctly to discover_stdio_tools
# ---------------------------------------------------------------------------


class TestTimeoutPropagation:
    def _invoke_with_timeout(self, timeout_arg: str | None) -> MagicMock:
        disc_result = StdioDiscoveryResult(success=True, schemas=(), server_name="srv")
        mock_discover = MagicMock(return_value=disc_result)
        args = ["stdio-discover", "srv"]
        if timeout_arg is not None:
            args += ["--timeout", timeout_arg]
        with (
            patch("safecode.cli_mcp.MCPConfigStore") as mock_store,
            patch("safecode.cli_mcp.Path.cwd", return_value=Path("/fake")),
            patch("safecode.cli_mcp.discover_stdio_tools", mock_discover),
        ):
            mock_store.return_value.list_servers.return_value = [
                MCPServerConfig("srv", "run-srv", argv=("python", "srv.py"))
            ]
            _runner.invoke(mcp_app, args)
        return mock_discover

    def test_custom_timeout_passed_to_discover(self) -> None:
        mock_discover = self._invoke_with_timeout("5.0")
        assert mock_discover.called
        _, kwargs = mock_discover.call_args
        assert kwargs["timeout_seconds"] == pytest.approx(5.0)

    def test_default_timeout_is_used_when_not_specified(self) -> None:
        mock_discover = self._invoke_with_timeout(None)
        assert mock_discover.called
        _, kwargs = mock_discover.call_args
        assert kwargs["timeout_seconds"] == pytest.approx(10.0)

    def test_timeout_1_second_passed_correctly(self) -> None:
        mock_discover = self._invoke_with_timeout("1.0")
        _, kwargs = mock_discover.call_args
        assert kwargs["timeout_seconds"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. StdioReadOnlyAdapter gates on static classification after merge
# ---------------------------------------------------------------------------


class TestAdapterGatesOnStaticClassificationAfterMerge:
    """When merged schemas are passed to the adapter, static classification governs."""

    def _make_adapter(
        self, merged: tuple[MCPToolSchema, ...], argv: list[str] | None = None
    ) -> StdioReadOnlyAdapter:
        return StdioReadOnlyAdapter(
            "srv",
            argv or ["python", "fake_srv.py"],
            schemas=list(merged),
            timeout_seconds=1.0,
        )

    def test_static_write_after_merge_blocks_tool(self) -> None:
        # Static says "write"; discovered says "unknown" — merged keeps "write"
        merged = merge_discovered_schemas(
            static=(_static("delete_files", "write"),),
            discovered=(_disc("delete_files"),),
        )
        adapter = self._make_adapter(merged)
        result = adapter.call_readonly("delete_files")
        assert result.blocked is True
        assert result.classification == "write"

    def test_static_read_after_merge_passes_gate(self, tmp_path: Path) -> None:
        # Static says "read"; discovered also found the tool — adapter should allow.
        # Use a real subprocess so we can verify it actually runs (or fails for other reasons).
        merged = merge_discovered_schemas(
            static=(_static("read_files", "read"),),
            discovered=(_disc("read_files"),),
        )
        adapter = self._make_adapter(merged, argv=["python", str(tmp_path / "nonexistent.py")])
        result = adapter.call_readonly("read_files")
        # Blocked=False: passed the classification gate (but transport fails because binary missing)
        assert result.blocked is False

    def test_discovered_only_unknown_blocked_after_merge(self) -> None:
        # Tool appears only in discovery (no static counterpart) → classification "unknown" → blocked
        merged = merge_discovered_schemas(
            static=(),
            discovered=(_disc("list_secrets"),),
        )
        assert merged[0].classification == "unknown"
        adapter = self._make_adapter(merged)
        result = adapter.call_readonly("list_secrets")
        assert result.blocked is True
        assert result.classification == "unknown"

    def test_classify_with_schema_respects_merged_static_write(self) -> None:
        merged = merge_discovered_schemas(
            static=(_static("rm_all", "write"),),
            discovered=(_disc("rm_all"),),
        )
        cls = classify_with_schema("rm_all", list(merged), server="srv")
        assert cls == "write"

    def test_classify_with_schema_discovered_only_returns_unknown(self) -> None:
        merged = merge_discovered_schemas(
            static=(),
            discovered=(_disc("mystery_tool"),),
        )
        # "mystery_tool" has classification "unknown" in merged; keyword fallback also gives unknown
        cls = classify_with_schema("mystery_tool", list(merged), server="srv")
        assert cls == "unknown"

    def test_adapter_blocks_discovered_only_tool_no_static(self) -> None:
        adapter = StdioReadOnlyAdapter(
            "srv",
            ["python", "fake.py"],
            schemas=[_disc("write_db")],
            timeout_seconds=1.0,
        )
        result = adapter.call_readonly("write_db")
        assert result.blocked is True


# ---------------------------------------------------------------------------
# 5. Shell string in TOML config fails at parse time, never reaches subprocess
# ---------------------------------------------------------------------------


class TestShellStringBlockedAtParse:
    def test_shell_string_argv_in_toml_raises_stdio_argv_error(self, tmp_path: Path) -> None:
        toml = tmp_path / ".sac" / "mcp.toml"
        toml.parent.mkdir(parents=True)
        toml.write_text(
            '[servers.myserver]\ncommand = "run"\nargv = "python srv.py"\n'
        )
        with pytest.raises(StdioArgvError, match="shell string"):
            MCPConfigStore(tmp_path).list_servers()

    def test_shell_string_error_text_does_not_contain_command(self, tmp_path: Path) -> None:
        toml = tmp_path / ".sac" / "mcp.toml"
        toml.parent.mkdir(parents=True)
        toml.write_text(
            '[servers.myserver]\ncommand = "run"\nargv = "rm -rf / --secret-token abc123"\n'
        )
        try:
            MCPConfigStore(tmp_path).list_servers()
        except StdioArgvError as exc:
            assert "rm -rf" not in str(exc)
            assert "abc123" not in str(exc)
        else:
            pytest.fail("Expected StdioArgvError")

    def test_non_string_argv_item_in_toml_raises_stdio_argv_error(self, tmp_path: Path) -> None:
        toml = tmp_path / ".sac" / "mcp.toml"
        toml.parent.mkdir(parents=True)
        toml.write_text(
            '[servers.myserver]\ncommand = "run"\nargv = ["python", 42]\n'
        )
        with pytest.raises(StdioArgvError):
            MCPConfigStore(tmp_path).list_servers()

    def test_empty_argv_in_toml_raises_stdio_argv_error(self, tmp_path: Path) -> None:
        toml = tmp_path / ".sac" / "mcp.toml"
        toml.parent.mkdir(parents=True)
        toml.write_text('[servers.myserver]\ncommand = "run"\nargv = []\n')
        with pytest.raises(StdioArgvError):
            MCPConfigStore(tmp_path).list_servers()

    def test_valid_argv_does_not_raise(self, tmp_path: Path) -> None:
        toml = tmp_path / ".sac" / "mcp.toml"
        toml.parent.mkdir(parents=True)
        toml.write_text(
            '[servers.myserver]\ncommand = "run"\nargv = ["python", "srv.py"]\n'
        )
        servers = MCPConfigStore(tmp_path).list_servers()
        assert servers[0].argv == ("python", "srv.py")


# ---------------------------------------------------------------------------
# 6. Oversized / malformed server responses fail closed at discovery level
# ---------------------------------------------------------------------------


class TestDiscoveryFailsClosedOnMalformedResponse:
    """Integration tests using real subprocesses to verify fail-closed behavior."""

    def _script(self, tmp_path: Path, body: str) -> list[str]:
        script = tmp_path / "srv.py"
        script.write_text(textwrap.dedent(body))
        return [sys.executable, str(script)]

    def test_oversized_tools_list_response_is_failure(self, tmp_path: Path) -> None:
        from safecode.mcp.discovery import discover_stdio_tools

        # Server returns more than 1 byte of output (way more than max_output_bytes=1)
        srv = self._script(
            tmp_path,
            """\
            import sys, json
            req = json.loads(sys.stdin.readline())
            # Return a response larger than the limit
            tools = [{"name": f"tool_{i}"} for i in range(1000)]
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
                               "result": {"tools": tools}}))
            """,
        )
        result = discover_stdio_tools("srv", srv, timeout_seconds=5.0, max_output_bytes=1)
        assert result.success is False

    def test_oversized_response_error_does_not_expose_content(self, tmp_path: Path) -> None:
        from safecode.mcp.discovery import discover_stdio_tools

        srv = self._script(
            tmp_path,
            """\
            import sys, json
            req = json.loads(sys.stdin.readline())
            secret = "SUPERSECRET_TOKEN_XYZ"
            tools = [{"name": f"tool_{i}_" + secret} for i in range(500)]
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
                               "result": {"tools": tools}}))
            """,
        )
        result = discover_stdio_tools("srv", srv, timeout_seconds=5.0, max_output_bytes=100)
        assert result.success is False
        assert "SUPERSECRET_TOKEN_XYZ" not in result.error

    def test_non_json_response_is_failure(self, tmp_path: Path) -> None:
        from safecode.mcp.discovery import discover_stdio_tools

        srv = self._script(
            tmp_path,
            """\
            import sys
            sys.stdin.readline()
            print("this is not json at all")
            """,
        )
        result = discover_stdio_tools("srv", srv, timeout_seconds=5.0)
        assert result.success is False

    def test_tools_list_with_injected_classification_gives_unknown_classification(
        self, tmp_path: Path
    ) -> None:
        from safecode.mcp.discovery import discover_stdio_tools

        srv = self._script(
            tmp_path,
            """\
            import sys, json
            req = json.loads(sys.stdin.readline())
            tools = [{"name": "read_all", "classification": "read",
                      "description": "Reads everything"}]
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
                               "result": {"tools": tools}}))
            """,
        )
        result = discover_stdio_tools("srv", srv, timeout_seconds=5.0)
        assert result.success is True
        assert len(result.schemas) == 1
        assert result.schemas[0].classification == "unknown"

    def test_timeout_during_discovery_fails_closed(self, tmp_path: Path) -> None:
        from safecode.mcp.discovery import discover_stdio_tools

        srv = self._script(
            tmp_path,
            """\
            import sys, time
            sys.stdin.readline()
            time.sleep(60)
            print("never reached")
            """,
        )
        result = discover_stdio_tools("srv", srv, timeout_seconds=0.15)
        assert result.success is False
        assert result.error


# ---------------------------------------------------------------------------
# 7. Error text from discovery/adapter never contains caller-supplied content
# ---------------------------------------------------------------------------


class TestErrorTextSafety:
    def test_stdio_argv_error_from_cli_does_not_contain_argv_values(self, tmp_path: Path) -> None:
        """CLI stdio-discover: StdioArgvError message must not expose argv item content."""
        from safecode.mcp.config import validate_stdio_argv

        secret_token = "MY_SECRET_API_KEY_12345"
        try:
            validate_stdio_argv(["python", secret_token])
        except StdioArgvError:
            pytest.fail("Valid argv raised StdioArgvError unexpectedly")

        # Now test an invalid item — error text must not include the secret
        try:
            validate_stdio_argv(["python", 999, secret_token])  # type: ignore[list-item]
        except StdioArgvError as exc:
            assert secret_token not in str(exc)
        else:
            pytest.fail("Expected StdioArgvError for non-string argv item")

    def test_adapter_write_block_error_does_not_contain_call_args(self, tmp_path: Path) -> None:
        secret = "SENSITIVE_PASSWORD_XYZ"
        adapter = StdioReadOnlyAdapter(
            "srv",
            ["python", "fake.py"],
            schemas=[_static("delete_files", "write")],
            timeout_seconds=1.0,
        )
        result = adapter.call_readonly("delete_files", {"password": secret})
        assert result.blocked is True
        assert secret not in result.error

    def test_adapter_unknown_block_error_does_not_contain_call_args(self) -> None:
        secret = "SECRET_TOKEN_9988"
        adapter = StdioReadOnlyAdapter(
            "srv",
            ["python", "fake.py"],
            schemas=[_static("mystery", "unknown")],
            timeout_seconds=1.0,
        )
        result = adapter.call_readonly("mystery", {"token": secret})
        assert result.blocked is True
        assert secret not in result.error

    def test_discovery_structural_error_does_not_contain_server_response(
        self, tmp_path: Path
    ) -> None:
        from safecode.mcp.discovery import discover_stdio_tools
        import textwrap

        # Server returns a "tools" value that is not a list, but with a secret embedded
        secret = "PRIVATE_DATA_ZZZ"
        script = tmp_path / "srv.py"
        script.write_text(
            textwrap.dedent(
                f"""\
                import sys, json
                req = json.loads(sys.stdin.readline())
                print(json.dumps({{"jsonrpc": "2.0", "id": req["id"],
                                   "result": {{"tools": "{secret}"}}}}))
                """
            )
        )
        result = discover_stdio_tools("srv", [sys.executable, str(script)], timeout_seconds=5.0)
        assert result.success is False
        assert secret not in result.error


# ---------------------------------------------------------------------------
# 8. Shell metacharacters in tool names are never shell-executed
# ---------------------------------------------------------------------------


class TestShellMetacharsInToolNameAreSafe:
    def test_tool_name_with_shell_meta_chars_is_blocked_by_classification(self) -> None:
        # A tool with a shell metacharacter name passes through the classification gate
        # as "unknown" (no static schema), which blocks it.
        adapter = StdioReadOnlyAdapter("srv", ["python", "fake.py"], timeout_seconds=1.0)
        result = adapter.call_readonly("; rm -rf /")
        assert result.blocked is True

    def test_tool_name_with_newline_is_blocked(self) -> None:
        adapter = StdioReadOnlyAdapter("srv", ["python", "fake.py"], timeout_seconds=1.0)
        result = adapter.call_readonly("tool\nmalicious")
        assert result.blocked is True

    def test_tool_name_with_backtick_is_blocked(self) -> None:
        adapter = StdioReadOnlyAdapter("srv", ["python", "fake.py"], timeout_seconds=1.0)
        result = adapter.call_readonly("`evil_command`")
        assert result.blocked is True

    def test_read_classified_tool_with_meta_chars_uses_shell_false(self, tmp_path: Path) -> None:
        """Even a read-classified tool with a weird name goes through shell=False."""
        script = tmp_path / "echo_srv.py"
        script.write_text(
            textwrap.dedent(
                """\
                import sys, json
                req = json.loads(sys.stdin.readline())
                print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
                                   "result": {"content": [{"type": "text", "text": "ok"}]}}))
                """
            )
        )
        # Tool name with spaces — read schema forces it through the gate
        weird_tool = "read with spaces"
        schema = _static(weird_tool, "read")
        adapter = StdioReadOnlyAdapter(
            "srv", [sys.executable, str(script)], schemas=[schema], timeout_seconds=5.0
        )
        result = adapter.call_readonly(weird_tool)
        # Should succeed (transport ran, shell=False means name wasn't executed)
        assert result.blocked is False
        assert result.success is True
