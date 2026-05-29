"""Tooling security eval suite for v1.6.5.

Organized security regression tests covering MCP, subagent, sandbox planning,
and cross-module boundaries. Each test is tagged with the v1.6.x version it
validates. This file complements tests/test_security_hardening.py with
additional focused coverage without duplicating existing tests.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig, merge_trusted_config
from safecode.policy.commands import CommandPolicy
from safecode.context.redactor import redact_secrets
from safecode.mcp.proposal import MCPWriteProposalStore
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapabilityDetector
from safecode.sandbox.planner import SandboxPlanner
from safecode.shell.runner import ShellRunner
from safecode.subagents.merge import MERGE_MARKER, SubagentMergeReviewer
from safecode.subagents.runner import ReadonlySubagentRunner
from safecode.subagents.task import SubagentTask, SubagentTaskStore, validate_task_id


# ── helpers ───────────────────────────────────────────────────────────


def _write_mock_mcp_server(tmp_path: Path) -> Path:
    path = tmp_path / "mock_mcp_server.py"
    path.write_text(
        textwrap.dedent(
            """
            import json, sys
            payload = json.loads(sys.stdin.read() or "{}")
            tool = payload.get("tool", "")
            if tool.endswith("secret"):
                output = "API_KEY=abc123"
            elif tool.endswith("large"):
                output = "A" * int(payload.get("input", {}).get("size", 0))
            else:
                output = {"ok": True, "input": payload.get("input", {})}
            print(json.dumps({"output": output}))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_mcp_config(tmp_path: Path, command: str) -> None:
    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir(parents=True, exist_ok=True)
    (sac_dir / "mcp.toml").write_text(
        textwrap.dedent(
            f"""
            [servers.mock]
            command = "{command}"
            enabled = true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


# ── 1. MCP security evals (v1.6.0 / v1.6.1) ─────────────────────────


class TestMCPNetworkBoundary:
    """Verify MCP calls cannot bypass network policy."""

    def test_network_disabled_blocks_readonly_call(self, tmp_path, monkeypatch):
        """v1.6.0: MCP read-only blocked when sandbox.network_enabled=False."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        server_path = _write_mock_mcp_server(tmp_path)
        command = shlex.join([sys.executable, str(server_path)])
        _write_mcp_config(tmp_path, command)

        config = SafeCodeConfig()
        config.shell.allowed_commands = [sys.executable]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = False

        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})
        assert result.blocked is True
        assert "Network access is disabled" in result.error


class TestMCPProposalSecurity:
    """Verify MCP write proposals are safe and audited."""

    def test_proposal_does_not_execute_subprocess(self, tmp_path, monkeypatch):
        """v1.6.1: write proposal must never launch a subprocess."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        _write_mcp_config(tmp_path, "echo ok")

        run_calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: run_calls.append(1))

        config = SafeCodeConfig()
        config.shell.allowed_commands = ["echo"]
        config.sandbox.network_enabled = True

        MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {"x": 1})
        assert len(run_calls) == 0

    def test_write_proposal_is_rejected_when_already_pending(self, tmp_path, monkeypatch):
        """v1.6.1: duplicate proposal fails closed."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        _write_mcp_config(tmp_path, "echo ok")

        config = SafeCodeConfig()
        config.shell.allowed_commands = ["echo"]
        config.sandbox.network_enabled = True

        runner = MCPReadOnlyRunner(tmp_path, config)
        runner.propose_write("mock", "mock.write", {"first": True})
        with pytest.raises(FileExistsError, match="already exists"):
            runner.propose_write("mock", "mock.create", {"second": True})

    def test_corrupt_pending_proposal_blocks_overwrite(self, tmp_path, monkeypatch):
        """v1.6.1: malformed pending proposal is not silently overwritten."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        _write_mcp_config(tmp_path, "echo ok")

        pending = tmp_path / ".sac" / "pending_mcp_call.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("{not valid json!!!", encoding="utf-8")

        config = SafeCodeConfig()
        config.shell.allowed_commands = ["echo"]
        config.sandbox.network_enabled = True

        with pytest.raises(FileExistsError, match="cannot be parsed"):
            MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {"x": 1})

    def test_unknown_tool_is_blocked_and_audited(self, tmp_path, monkeypatch):
        """v1.6.1: unknown tool classification writes audit event."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        _write_mcp_config(tmp_path, "echo ok")

        config = SafeCodeConfig()
        config.shell.allowed_commands = ["echo"]
        config.sandbox.network_enabled = True

        runner = MCPReadOnlyRunner(tmp_path, config)
        with pytest.raises(PermissionError):
            runner.propose_write("mock", "mock.xyzzy", {})

        events = AuditLogger(tmp_path, config).read_recent(limit=5)
        assert any(e.type == "mcp_write_blocked" for e in events)


# ── 2. Subagent security evals (v1.6.2 / v1.6.3) ─────────────────────


class TestSubagentBoundary:
    """Verify subagent isolation holds."""

    def test_runner_cannot_write_business_files(self, tmp_path, monkeypatch):
        """v1.6.2: subagent result must never touch business files."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")

        result = ReadonlySubagentRunner(tmp_path).run("inspect", "read project")
        assert result.executed is True
        assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print('hello')\n"

    def test_result_redacts_secrets_from_context(self, tmp_path, monkeypatch):
        """v1.6.2: subagent context collection redacts secrets."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        (tmp_path / "README.md").write_text("SECRET_TOKEN=ghp_abc123def456\n", encoding="utf-8")

        result = ReadonlySubagentRunner(tmp_path).run("inspect", "read secrets")
        content = result.result_path.read_text(encoding="utf-8")
        assert "ghp_abc123def456" not in content


class TestMergeReviewBoundary:
    """Verify merge review safety."""

    def test_merge_does_not_modify_target_file(self, tmp_path, monkeypatch):
        """v1.6.3: merge-review is proposal-only, never writes business files."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        target = tmp_path / "REVIEW.md"
        original = f"# Review\n\n{MERGE_MARKER}\n"
        target.write_text(original, encoding="utf-8")

        runner = ReadonlySubagentRunner(tmp_path)
        r = runner.run("inspect", "read project")
        SubagentMergeReviewer(tmp_path).propose([r.task.id], "REVIEW.md")

        assert target.read_text(encoding="utf-8") == original

    def test_merge_redacts_secrets_in_pending_patch(self, tmp_path, monkeypatch):
        """v1.6.3: secrets from subagent results are redacted before patch."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        (tmp_path / "README.md").write_text("API_KEY=sk-topsecret\n", encoding="utf-8")
        target = tmp_path / "REVIEW.md"
        target.write_text(f"# R\n\n{MERGE_MARKER}\n", encoding="utf-8")

        runner = ReadonlySubagentRunner(tmp_path)
        r = runner.run("inspect", "read project")
        SubagentMergeReviewer(tmp_path).propose([r.task.id], "REVIEW.md")

        pending = tmp_path / ".sac" / "pending_patch.json"
        content = pending.read_text(encoding="utf-8")
        assert "sk-topsecret" not in content
        assert "[REDACTED]" in content

    def test_merge_rejects_result_path_outside_subagents(self, tmp_path, monkeypatch):
        """v1.6.3: result outside .sac/subagents/ is rejected."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        target = tmp_path / "REVIEW.md"
        target.write_text(f"# R\n\n{MERGE_MARKER}\n", encoding="utf-8")

        outside = tmp_path / "outside.md"
        outside.write_text("# Bad\n", encoding="utf-8")
        store = SubagentTaskStore(tmp_path)
        task = SubagentTask(
            id="abc123def456",
            title="bad",
            instructions="x",
            readonly=True,
            status="completed",
            result_path=str(outside),
        )
        store._write_task(task)

        with pytest.raises(PermissionError, match="outside"):
            SubagentMergeReviewer(tmp_path).propose(["abc123def456"], "REVIEW.md")


# ── 3. Sandbox planning regression (v1.6.4) ──────────────────────────


class TestSandboxPlanningRegression:
    """Verify sandbox detection stays safe."""

    def test_detector_never_calls_subprocess(self, monkeypatch):
        """v1.6.4: detection uses platform + shutil.which only."""
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "call", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        SandboxCapabilityDetector().detect_all()
        assert len(called) == 0

    def test_docker_only_detects_not_starts(self, monkeypatch):
        """v1.6.4: docker detection is via shutil.which, never docker run."""
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None)
        cap = SandboxCapabilityDetector()._detect_docker()
        assert cap.available is True
        assert cap.filesystem_isolation_supported is True

    def test_fallback_none_lists_active_boundaries(self, monkeypatch, tmp_path):
        """v1.6.4: none backend plan must list logical boundaries."""
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setattr("platform.system", lambda: "FreeBSD")

        plan = SandboxPlanner(tmp_path).plan()
        assert plan.recommended_backend == SandboxBackend.NONE
        assert "command_policy" in plan.active_logical_boundaries
        assert "filesystem_boundary" in plan.active_logical_boundaries
        assert "network_policy" in plan.active_logical_boundaries
        assert "audit_log" in plan.active_logical_boundaries

    def test_status_writes_audit_event(self, tmp_path, monkeypatch):
        """v1.6.4: planner writes sandbox_status_checked audit event."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))

        SandboxPlanner(tmp_path).plan()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        sandbox_events = [e for e in events if e.type == "sandbox_status_checked"]
        assert len(sandbox_events) >= 1
        ev = sandbox_events[0]
        assert "platform" in ev.metadata
        assert "recommended_backend" in ev.metadata
        assert "available_backends" in ev.metadata


# ── 4. Cross-module security boundaries (v1.6.x) ──────────────────────


class TestNetworkPolicyCrossModule:
    """Network policy is enforced consistently across shell and MCP."""

    def test_shell_blocked_when_network_disabled(self):
        """v1.5.22: shell runner blocks network commands."""
        config = SafeCodeConfig()
        config.shell.allowed_commands = ["git", "curl", "npm"]
        runner = ShellRunner(Path("/tmp"), config)

        for cmd in ["git fetch", "curl https://example.com", "npm install x"]:
            result = runner.run(cmd, approved=True)
            assert result.executed is False

    def test_mcp_blocked_when_network_disabled(self, tmp_path, monkeypatch):
        """v1.6.0: MCP calls blocked when network is off."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        _write_mcp_config(tmp_path, "echo ok")

        config = SafeCodeConfig()
        config.shell.allowed_commands = ["echo"]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = False

        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})
        assert result.blocked is True

    def test_user_config_cannot_enable_unsafe_network(self):
        """v1.2.1: project config cannot enable network if user disabled it."""
        user = SafeCodeConfig(policy="strict")
        project = SafeCodeConfig()
        project.sandbox.network_enabled = True
        merged = merge_trusted_config(user, project)
        assert merged.sandbox.network_enabled is False


class TestSecretRedactionConsistency:
    """Secret redaction produces consistent results across modules."""

    def test_redact_secrets_removes_aws_keys(self):
        result = redact_secrets("key=AKIA1234567890ABCDEF secret")
        assert "AKIA1234567890ABCDEF" not in result
        assert "[REDACTED]" in result

    def test_redact_secrets_removes_github_tokens(self):
        result = redact_secrets("token=ghp_1234567890abcdef1234567890abcdef1234")
        assert "ghp_1234567890abcdef1234567890abcdef1234" not in result
        assert "[REDACTED]" in result

    def test_redact_secrets_removes_bearer_tokens(self):
        result = redact_secrets("Authorization: Bearer abcdef1234567890abcdef1234567890")
        assert "abcdef1234567890abcdef1234567890" not in result
        assert "[REDACTED]" in result

    def test_redact_secrets_preserves_non_secret_content(self):
        original = "This is normal text with no secrets."
        result = redact_secrets(original)
        assert result == original

    def test_mcp_output_redaction_uses_same_redactor(self, tmp_path, monkeypatch):
        """v1.6.0: MCP output secret redaction uses the shared redactor."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        server_path = _write_mock_mcp_server(tmp_path)
        command = shlex.join([sys.executable, str(server_path)])
        _write_mcp_config(tmp_path, command)

        config = SafeCodeConfig()
        config.shell.allowed_commands = [sys.executable]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = True

        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.get_secret", {})
        assert result.blocked is False
        assert "abc123" not in result.output
        assert "[REDACTED]" in result.output


class TestApprovalPathSecurity:
    """Approval and audit anchor paths are protected."""

    def test_audit_anchor_rejects_project_local_dir(self, tmp_path, monkeypatch):
        """v1.5.17: anchor dir inside project root is rejected."""
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
        with pytest.raises(PermissionError, match="outside"):
            AuditLogger(tmp_path)

    def test_audit_anchor_allows_external_dir(self, tmp_path, monkeypatch):
        """v1.5.17: anchor dir outside project root is allowed."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        logger = AuditLogger(tmp_path)
        logger.write(AuditEvent(type="test", timestamp="2026-01-01T00:00:00Z", message="ok"))
        assert any(anchor_dir.glob("*.jsonl"))

    def test_approval_dir_rejects_project_root(self, tmp_path, monkeypatch):
        """v1.5.23: approval dir inside project root is rejected."""
        from safecode.hooks.approvals import HookApprovalStore
        monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / ".sac" / "approvals"))
        with pytest.raises(PermissionError, match="outside"):
            HookApprovalStore(tmp_path, SafeCodeConfig())


class TestConfigCannotLowerSecurity:
    """Project config must never weaken user-level security settings."""

    def test_policy_is_strict_when_user_is_strict(self):
        user = SafeCodeConfig(policy="strict")
        project = SafeCodeConfig(policy="learning")
        merged = merge_trusted_config(user, project)
        assert merged.policy == "strict"

    def test_block_high_risk_cannot_be_disabled_by_project(self):
        user = SafeCodeConfig()
        project = SafeCodeConfig()
        project.shell.block_high_risk = False
        merged = merge_trusted_config(user, project)
        assert merged.shell.block_high_risk is True

    def test_require_confirm_cannot_be_disabled_by_project(self):
        user = SafeCodeConfig()
        project = SafeCodeConfig()
        project.shell.require_confirm_for_medium = False
        merged = merge_trusted_config(user, project)
        assert merged.shell.require_confirm_for_medium is True

    def test_network_cannot_be_enabled_by_project(self):
        user = SafeCodeConfig()
        project = SafeCodeConfig()
        project.sandbox.network_enabled = True
        merged = merge_trusted_config(user, project)
        assert merged.sandbox.network_enabled is False


class TestCommandPolicyCrossModule:
    """Command policy is shared across shell, hooks, and MCP."""

    def test_shell_high_risk_blocked_even_with_approval(self, tmp_path):
        """v1.2.0: high-risk commands are always blocked."""
        result = ShellRunner(tmp_path).run("rm -rf /tmp/safecode-example", approved=True)
        assert result.executed is False

    def test_shell_non_allowlisted_blocked(self):
        """v1.5.2: non-allowlisted commands are blocked."""
        decision = CommandPolicy(SafeCodeConfig()).evaluate("curl https://example.com", approved=True)
        assert decision.allowed is False

    def test_hook_injection_blocked_by_command_policy(self, tmp_path):
        """v1.5.3: hook commands go through command policy."""
        from safecode.hooks.runner import HookRunner
        config = SafeCodeConfig()
        config.hooks.after_apply = ["rm -rf /tmp/safecode-hook"]
        summary = HookRunner(tmp_path, config).run_after_apply()
        assert summary.results[0].executed is False


# ── 5. Regression: existing suites still pass ─────────────────────────


class TestExistingSuiteRegression:
    """Smoke tests verifying v1.6.0-v1.6.4 core paths still work."""

    def test_mcp_readonly_works(self, tmp_path, monkeypatch):
        """v1.6.0 regression."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        server_path = _write_mock_mcp_server(tmp_path)
        command = shlex.join([sys.executable, str(server_path)])
        _write_mcp_config(tmp_path, command)

        config = SafeCodeConfig()
        config.shell.allowed_commands = [sys.executable]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = True

        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {"q": "test"})
        assert result.blocked is False
        assert result.exit_code == 0

    def test_mcp_write_proposal_works(self, tmp_path, monkeypatch):
        """v1.6.1 regression."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        _write_mcp_config(tmp_path, "echo ok")

        config = SafeCodeConfig()
        config.shell.allowed_commands = ["echo"]
        config.sandbox.network_enabled = True

        proposal = MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {"k": "v"})
        assert proposal.classification == "write"
        assert proposal.status == "pending"

    def test_subagent_readonly_works(self, tmp_path, monkeypatch):
        """v1.6.2 regression."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")

        result = ReadonlySubagentRunner(tmp_path).run("inspect", "read project")
        assert result.executed is True
        assert result.result_path is not None

    def test_subagent_merge_works(self, tmp_path, monkeypatch):
        """v1.6.3 regression."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
        target = tmp_path / "REVIEW.md"
        target.write_text(f"# R\n\n{MERGE_MARKER}\n", encoding="utf-8")

        runner = ReadonlySubagentRunner(tmp_path)
        r = runner.run("inspect", "read project")
        mr = SubagentMergeReviewer(tmp_path).propose([r.task.id], "REVIEW.md")
        assert mr.diff_text

    def test_sandbox_status_works(self, tmp_path, monkeypatch):
        """v1.6.4 regression."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))

        plan = SandboxPlanner(tmp_path).plan()
        assert plan.recommended_backend is not None
        assert len(plan.capabilities) == 4
