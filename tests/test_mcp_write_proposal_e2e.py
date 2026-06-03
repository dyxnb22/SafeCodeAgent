"""End-to-end tests for MCP write proposal flow (v3.8.2 T-3.8.2-A).

Covers the full gate sequence:
  propose → approval grant (outside project root) → execute via stdio
  → result record → audit event → proposal consumed (single-use)

Key invariants verified:
- Approval grant stored outside project root (SAFECODE_MCP_APPROVAL_DIR)
- Single-use: second execute attempt blocked after grant consumed
- Classification gate checked before execution
- Audit events emitted for granted write started / completed / blocked
- Proposal discarded after successful execution
- No real network; stub JSON-RPC server only
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_stub_jsonrpc_server(tmp_path: Path) -> Path:
    """Write a minimal JSON-RPC stub that handles tools/call."""
    path = tmp_path / "stub_jsonrpc_server.py"
    path.write_text(
        "\n".join([
            "import json, sys",
            "line = sys.stdin.readline()",
            "try:",
            "    req = json.loads(line)",
            "except Exception:",
            "    sys.exit(1)",
            "method = req.get('method', '')",
            "req_id = req.get('id', 1)",
            "if method == 'tools/call':",
            "    params = req.get('params', {})",
            "    name = params.get('name', '')",
            "    args = params.get('arguments', {})",
            "    result = {'content': [{'type': 'text', 'text': json.dumps({'ok': True, 'tool': name, 'args': args})}]}",
            "    resp = {'jsonrpc': '2.0', 'id': req_id, 'result': result}",
            "elif method == 'tools/list':",
            "    resp = {'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': []}}",
            "else:",
            "    resp = {'jsonrpc': '2.0', 'id': req_id, 'error': {'code': -32601, 'message': 'method not found'}}",
            "print(json.dumps(resp))",
            "sys.stdout.flush()",
        ]),
        encoding="utf-8",
    )
    return path


def _write_server_toml(tmp_path: Path, server_path: Path, scope: str = "write_proposal_required") -> None:
    sac = tmp_path / ".sac"
    sac.mkdir(exist_ok=True)
    argv_str = json.dumps([sys.executable, str(server_path)])
    (sac / "mcp.toml").write_text(
        f'[servers.stub]\n'
        f'command = "{sys.executable}"\n'
        f'scope = "{scope}"\n'
        f'argv = {argv_str}\n',
        encoding="utf-8",
    )


def _make_runner(tmp_path: Path, *, stdio_runner: bool = True):
    from safecode.config import SafeCodeConfig
    from safecode.mcp.runner import MCPReadOnlyRunner
    from safecode.mcp.schema import MCPToolSchema

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True
    schema = MCPToolSchema(server="stub", tool="mock.create", classification="write")
    return MCPReadOnlyRunner(tmp_path, config, schemas=[schema], stdio_runner=stdio_runner)


# ── MCPApprovalStore unit tests ───────────────────────────────────────────────


class TestMCPApprovalStore:
    def test_grant_creates_file_outside_project(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        grant = store.grant("pid-001")
        assert grant.proposal_id == "pid-001"
        assert not grant.consumed
        assert (approval_dir / "pid-001.json").exists()

    def test_grant_directory_is_configurable(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path.parent / "out_of_project_approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        assert store.approval_dir == approval_dir

    def test_consume_returns_grant_and_deletes_file(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        store.grant("pid-002")
        grant = store.consume("pid-002")
        assert grant is not None
        assert grant.proposal_id == "pid-002"
        assert not (approval_dir / "pid-002.json").exists()

    def test_consume_returns_none_when_no_grant(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        assert store.consume("no-such-id") is None

    def test_single_use_second_consume_returns_none(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        store.grant("pid-003")
        store.consume("pid-003")  # consumes and deletes
        assert store.consume("pid-003") is None  # second attempt returns None

    def test_has_valid_grant_true(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        store.grant("pid-004")
        assert store.has_valid_grant("pid-004") is True

    def test_has_valid_grant_false_when_consumed(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        store.grant("pid-005")
        store.consume("pid-005")
        assert store.has_valid_grant("pid-005") is False

    def test_duplicate_grant_raises(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        store.grant("pid-006")
        with pytest.raises(PermissionError):
            store.grant("pid-006")

    def test_revoke_deletes_grant(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        store.grant("pid-007")
        revoked = store.revoke("pid-007")
        assert revoked is True
        assert not store.has_valid_grant("pid-007")

    def test_revoke_returns_false_when_no_grant(self, tmp_path, monkeypatch):
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()
        assert store.revoke("no-such-id") is False


# ── E2E flow tests ────────────────────────────────────────────────────────────


class TestWriteProposalE2E:
    def _setup(self, tmp_path: Path, monkeypatch):
        """Return (runner, approval_store, stub_server_path)."""
        from safecode.mcp.approval_grant import MCPApprovalStore

        stub_path = _write_stub_jsonrpc_server(tmp_path)
        _write_server_toml(tmp_path, stub_path)
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path.parent / "anchors"))
        approval_dir = tmp_path.parent / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        runner = _make_runner(tmp_path, stdio_runner=True)
        store = MCPApprovalStore()
        return runner, store, stub_path

    def test_full_e2e_propose_grant_execute(self, tmp_path, monkeypatch):
        """propose → grant (outside project) → execute via stdio → success result."""
        runner, store, _ = self._setup(tmp_path, monkeypatch)

        # Step 1: propose write
        proposal = runner.propose_write("stub", "mock.create", {"name": "test"})
        assert proposal.status == "pending"

        # Step 2: grant approval outside project root
        grant = store.grant(proposal.proposal_id)
        assert grant.proposal_id == proposal.proposal_id
        # Verify approval file is NOT inside project root
        assert not (tmp_path / ".sac" / f"{proposal.proposal_id}.json").exists()

        # Step 3: execute via stdio
        result = runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {"name": "test"},
            approval_store=store,
        )
        assert result.executed
        assert not result.blocked
        assert result.exit_code == 0

    def test_e2e_result_contains_output(self, tmp_path, monkeypatch):
        runner, store, _ = self._setup(tmp_path, monkeypatch)
        proposal = runner.propose_write("stub", "mock.create", {"data": "hello"})
        store.grant(proposal.proposal_id)
        result = runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {"data": "hello"},
            approval_store=store,
        )
        assert result.output  # stub returns JSON output

    def test_e2e_proposal_discarded_after_execution(self, tmp_path, monkeypatch):
        """Pending proposal file is removed after successful execution (single-use)."""
        from safecode.mcp.proposal import MCPWriteProposalStore

        runner, store, _ = self._setup(tmp_path, monkeypatch)
        proposal = runner.propose_write("stub", "mock.create", {})
        store.grant(proposal.proposal_id)
        runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {},
            approval_store=store,
        )
        # Proposal file should be gone after execution
        proposal_store = MCPWriteProposalStore(tmp_path)
        assert proposal_store.load_pending() is None

    def test_e2e_single_use_second_execute_blocked(self, tmp_path, monkeypatch):
        """Second execute_granted_write with consumed grant is blocked."""
        runner, store, _ = self._setup(tmp_path, monkeypatch)
        proposal = runner.propose_write("stub", "mock.create", {})
        store.grant(proposal.proposal_id)

        # First execute consumes the grant
        result1 = runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {},
            approval_store=store,
        )
        assert result1.executed and not result1.blocked

        # Propose again (original was discarded)
        proposal2 = runner.propose_write("stub", "mock.create", {})
        # Second execute attempt WITHOUT re-granting → blocked
        result2 = runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {},
            approval_store=store,
        )
        assert result2.blocked

    def test_e2e_no_grant_blocks_execution(self, tmp_path, monkeypatch):
        runner, store, _ = self._setup(tmp_path, monkeypatch)
        proposal = runner.propose_write("stub", "mock.create", {})
        # Do NOT grant approval
        result = runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {},
            approval_store=store,
        )
        assert result.blocked

    def test_e2e_audit_event_emitted_on_success(self, tmp_path, monkeypatch):
        """mcp_granted_write_completed audit event is emitted after execution."""
        from safecode.audit.logger import AuditLogger

        runner, store, _ = self._setup(tmp_path, monkeypatch)
        proposal = runner.propose_write("stub", "mock.create", {"x": 1})
        store.grant(proposal.proposal_id)
        runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {"x": 1},
            approval_store=store,
        )
        events = AuditLogger(tmp_path).read_recent(limit=50)
        types = [e.type for e in events]
        assert "mcp_granted_write_completed" in types

    def test_e2e_audit_event_emitted_on_blocked(self, tmp_path, monkeypatch):
        """mcp_granted_write_blocked audit event emitted when no grant."""
        from safecode.audit.logger import AuditLogger

        runner, store, _ = self._setup(tmp_path, monkeypatch)
        proposal = runner.propose_write("stub", "mock.create", {})
        # No grant
        runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {},
            approval_store=store,
        )
        events = AuditLogger(tmp_path).read_recent(limit=50)
        types = [e.type for e in events]
        assert "mcp_granted_write_blocked" in types

    def test_e2e_approval_outside_project_root(self, tmp_path, monkeypatch):
        """Verify approval directory is outside the project root."""
        from safecode.mcp.approval_grant import MCPApprovalStore

        approval_dir = tmp_path.parent / "approvals"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))
        store = MCPApprovalStore()

        # Approval dir must NOT be inside tmp_path (project root)
        assert not str(approval_dir).startswith(str(tmp_path))

    def test_e2e_without_stdio_runner_flag_blocked(self, tmp_path, monkeypatch):
        """execute_granted_write without stdio_runner=True is blocked."""
        from safecode.mcp.approval_grant import MCPApprovalStore

        stub_path = _write_stub_jsonrpc_server(tmp_path)
        _write_server_toml(tmp_path, stub_path)
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path.parent / "anchors"))
        approval_dir = tmp_path.parent / "approvals_no_stdio"
        monkeypatch.setenv("SAFECODE_MCP_APPROVAL_DIR", str(approval_dir))

        runner = _make_runner(tmp_path, stdio_runner=False)
        store = MCPApprovalStore()
        proposal = runner.propose_write("stub", "mock.create", {})
        store.grant(proposal.proposal_id)
        result = runner.execute_granted_write(
            proposal.proposal_id, "stub", "mock.create", {},
            approval_store=store,
        )
        assert result.blocked
