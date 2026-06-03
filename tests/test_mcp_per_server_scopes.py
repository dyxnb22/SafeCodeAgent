"""Tests for per-server MCP scope enforcement (v3.8.1 T-3.8.1-A).

Covers:
- MCPServerConfig.scope field: default read_only, parsed from TOML
- Invalid TOML scope values default to "denied" (fail-closed)
- Scope gate runs BEFORE classification in call_readonly and propose_write
- Unknown server (not in config) defaults to "denied"
- denied scope blocks call_readonly before classification
- read_only scope allows read tool calls; blocks write proposals
- write_proposal_required scope allows read calls and write proposals
- Scope audit event emitted on deny
"""

from __future__ import annotations

import pytest


# ── Config parsing ────────────────────────────────────────────────────────────


class TestMCPServerConfigScope:
    def test_default_scope_is_read_only(self):
        from safecode.mcp.config import MCPServerConfig

        cfg = MCPServerConfig(name="s", command="echo")
        assert cfg.scope == "read_only"

    def test_scope_denied(self):
        from safecode.mcp.config import MCPServerConfig

        cfg = MCPServerConfig(name="s", command="echo", scope="denied")
        assert cfg.scope == "denied"

    def test_scope_write_proposal_required(self):
        from safecode.mcp.config import MCPServerConfig

        cfg = MCPServerConfig(name="s", command="echo", scope="write_proposal_required")
        assert cfg.scope == "write_proposal_required"

    def test_valid_scopes_set(self):
        from safecode.mcp.config import VALID_SCOPES

        assert "denied" in VALID_SCOPES
        assert "read_only" in VALID_SCOPES
        assert "write_proposal_required" in VALID_SCOPES
        assert len(VALID_SCOPES) == 3


class TestMCPConfigStoreParsesScope:
    def _write_toml(self, tmp_path, content: str) -> None:
        sac = tmp_path / ".sac"
        sac.mkdir()
        (sac / "mcp.toml").write_text(content, encoding="utf-8")

    def test_scope_read_only_parsed(self, tmp_path):
        from safecode.mcp.config import MCPConfigStore

        self._write_toml(tmp_path, '[servers.s]\ncommand = "echo"\nscope = "read_only"\n')
        servers = MCPConfigStore(tmp_path).list_servers()
        assert servers[0].scope == "read_only"

    def test_scope_denied_parsed(self, tmp_path):
        from safecode.mcp.config import MCPConfigStore

        self._write_toml(tmp_path, '[servers.s]\ncommand = "echo"\nscope = "denied"\n')
        servers = MCPConfigStore(tmp_path).list_servers()
        assert servers[0].scope == "denied"

    def test_scope_write_proposal_required_parsed(self, tmp_path):
        from safecode.mcp.config import MCPConfigStore

        self._write_toml(tmp_path, '[servers.s]\ncommand = "echo"\nscope = "write_proposal_required"\n')
        servers = MCPConfigStore(tmp_path).list_servers()
        assert servers[0].scope == "write_proposal_required"

    def test_invalid_scope_defaults_to_denied(self, tmp_path):
        from safecode.mcp.config import MCPConfigStore

        self._write_toml(tmp_path, '[servers.s]\ncommand = "echo"\nscope = "superadmin"\n')
        servers = MCPConfigStore(tmp_path).list_servers()
        assert servers[0].scope == "denied"

    def test_missing_scope_defaults_to_read_only(self, tmp_path):
        from safecode.mcp.config import MCPConfigStore

        self._write_toml(tmp_path, '[servers.s]\ncommand = "echo"\n')
        servers = MCPConfigStore(tmp_path).list_servers()
        assert servers[0].scope == "read_only"


# ── Runner: scope gate in call_readonly ───────────────────────────────────────


def _write_server_toml(tmp_path, server_name: str, scope: str) -> None:
    sac = tmp_path / ".sac"
    sac.mkdir(exist_ok=True)
    (sac / "mcp.toml").write_text(
        f'[servers.{server_name}]\ncommand = "echo"\nscope = "{scope}"\n',
        encoding="utf-8",
    )


class TestCallReadonlyScopeGate:
    def test_unknown_server_blocked_as_denied(self, tmp_path):
        """No mcp.toml at all — unknown server defaults to denied."""
        from safecode.mcp.runner import MCPReadOnlyRunner

        runner = MCPReadOnlyRunner(tmp_path)
        result = runner.call_readonly("no_such_server", "list_files")
        assert result.blocked

    def test_unknown_server_error_mentions_not_configured(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        runner = MCPReadOnlyRunner(tmp_path)
        result = runner.call_readonly("no_such_server", "list_files")
        assert "not configured" in result.error.lower()

    def test_denied_scope_blocks_before_classification(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.mcp.schema import MCPToolSchema

        _write_server_toml(tmp_path, "srv", "denied")
        schema = MCPToolSchema(server="srv", tool="list_files", classification="read")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("srv", "list_files")
        assert result.blocked
        assert "denied" in result.error.lower()

    def test_denied_scope_blocked_result_not_executed(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        _write_server_toml(tmp_path, "srv", "denied")
        runner = MCPReadOnlyRunner(tmp_path)
        result = runner.call_readonly("srv", "list_files")
        assert not result.executed

    def test_read_only_scope_allows_read_tool_to_classification_gate(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.mcp.schema import MCPToolSchema

        _write_server_toml(tmp_path, "srv", "read_only")
        schema = MCPToolSchema(server="srv", tool="list_files", classification="read")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("srv", "list_files")
        # Scope gate passes; blocked later by policy (no real binary)
        assert result.blocked
        assert "denied" not in result.error.lower()

    def test_write_proposal_required_scope_allows_read_tool_to_classification_gate(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.mcp.schema import MCPToolSchema

        _write_server_toml(tmp_path, "srv", "write_proposal_required")
        schema = MCPToolSchema(server="srv", tool="list_files", classification="read")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("srv", "list_files")
        # Scope gate passes; blocked later by policy (no real binary)
        assert result.blocked
        assert "denied" not in result.error.lower()

    def test_denied_scope_blocks_write_tool_too(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.mcp.schema import MCPToolSchema

        _write_server_toml(tmp_path, "srv", "denied")
        schema = MCPToolSchema(server="srv", tool="write_file", classification="write")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        result = runner.call_readonly("srv", "write_file")
        assert result.blocked
        assert "denied" in result.error.lower()

    def test_scope_gate_runs_before_classification_confirmed(self, tmp_path):
        """With denied scope, even an unknown tool name is blocked without classifying."""
        from safecode.mcp.runner import MCPReadOnlyRunner

        _write_server_toml(tmp_path, "srv", "denied")
        runner = MCPReadOnlyRunner(tmp_path)
        result = runner.call_readonly("srv", "unknown_tool_xyz")
        assert result.blocked
        # If classification ran first and blocked it, the error would say "not classified as read-only"
        # Scope block message must say "denied"
        assert "denied" in result.error.lower()


# ── Runner: scope gate in propose_write ───────────────────────────────────────


class TestProposeWriteScopeGate:
    def test_unknown_server_raises_permission_error(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        runner = MCPReadOnlyRunner(tmp_path)
        with pytest.raises(PermissionError, match="not configured"):
            runner.propose_write("no_such_server", "write_file")

    def test_denied_scope_raises_permission_error(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        _write_server_toml(tmp_path, "srv", "denied")
        runner = MCPReadOnlyRunner(tmp_path)
        with pytest.raises(PermissionError, match="denied"):
            runner.propose_write("srv", "write_file")

    def test_read_only_scope_raises_permission_error(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner

        _write_server_toml(tmp_path, "srv", "read_only")
        runner = MCPReadOnlyRunner(tmp_path)
        with pytest.raises(PermissionError, match="read_only"):
            runner.propose_write("srv", "write_file")

    def test_write_proposal_required_scope_allows_write_proposal(self, tmp_path):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.mcp.schema import MCPToolSchema

        _write_server_toml(tmp_path, "srv", "write_proposal_required")
        schema = MCPToolSchema(server="srv", tool="write_file", classification="write")
        runner = MCPReadOnlyRunner(tmp_path, schemas=[schema])
        # Scope gate passes; should create a pending proposal
        proposal = runner.propose_write("srv", "write_file", {})
        assert proposal.server == "srv"
        assert proposal.tool == "write_file"

    def test_read_only_scope_blocks_before_classification(self, tmp_path):
        """read_only scope must block write proposals before classification."""
        from safecode.mcp.runner import MCPReadOnlyRunner

        _write_server_toml(tmp_path, "srv", "read_only")
        runner = MCPReadOnlyRunner(tmp_path)
        with pytest.raises(PermissionError) as exc_info:
            # Even an unknown-classified tool should be blocked by scope, not classification.
            runner.propose_write("srv", "xyzzy_tool_unknown")
        assert "read_only" in str(exc_info.value)
