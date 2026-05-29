"""Sandbox adapter contract tests for v1.7.0.

Verifies that all adapters build dry-run plans without executing commands,
and that the factory integrates correctly with policy and planner.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.factory import SandboxAdapterFactory


# ── helpers ───────────────────────────────────────────────────────────

def _make_request(command=None, **kwargs):
    defaults = {
        "command": command or ["echo", "hello"],
        "cwd": Path("/tmp/test"),
        "purpose": "shell",
        "allow_network": False,
        "readonly_filesystem": True,
        "writable_paths": [],
        "env": {},
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return SandboxExecutionRequest(**defaults)


# ── adapter contract tests ────────────────────────────────────────────


class TestNoopAdapter:
    def test_build_plan_returns_dry_run_true(self):
        plan = NoopSandboxAdapter().build_plan(_make_request())
        assert plan.dry_run is True
        assert plan.backend == SandboxBackend.NONE

    def test_supports_execution_is_false(self):
        assert NoopSandboxAdapter().supports_execution() is False

    def test_env_values_not_in_plan(self):
        plan = NoopSandboxAdapter().build_plan(
            _make_request(env={"SECRET_KEY": "abc123", "HOME": "/home"})
        )
        assert "abc123" not in str(plan.env_keys)
        assert "SECRET_KEY" in plan.env_keys
        assert "abc123" not in plan.cwd
        assert "abc123" not in " ".join(plan.warnings)
        assert "abc123" not in " ".join(plan.limitations)


class TestMacOSSeatbeltAdapter:
    def test_build_plan_no_subprocess(self, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["macOS"],
            reason="test",
            limitations=["limitation a"],
        )
        plan = MacOSSeatbeltAdapter(cap).build_plan(_make_request())
        assert plan.dry_run is True
        assert plan.backend == SandboxBackend.MACOS_SEATBELT
        assert len(called) == 0

    def test_supports_execution_is_false(self):
        cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["macOS"],
            reason="test",
        )
        assert MacOSSeatbeltAdapter(cap).supports_execution() is False


class TestLinuxBubblewrapAdapter:
    def test_build_plan_no_subprocess(self, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["Linux"],
            reason="test",
            limitations=["needs userns"],
        )
        plan = LinuxBubblewrapAdapter(cap).build_plan(_make_request())
        assert plan.dry_run is True
        assert plan.backend == SandboxBackend.LINUX_BUBBLEWRAP
        assert len(called) == 0

    def test_supports_execution_is_false(self):
        cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["Linux"],
            reason="test",
        )
        assert LinuxBubblewrapAdapter(cap).supports_execution() is False


class TestDockerAdapter:
    def test_build_plan_no_subprocess(self, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        cap = SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=True,
            supported_platforms=["all"],
            reason="test",
            limitations=["needs daemon"],
        )
        plan = DockerSandboxAdapter(cap).build_plan(_make_request())
        assert plan.dry_run is True
        assert plan.backend == SandboxBackend.DOCKER
        assert len(called) == 0

    def test_supports_execution_is_false(self):
        cap = SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=True,
            supported_platforms=["all"],
            reason="test",
        )
        assert DockerSandboxAdapter(cap).supports_execution() is False


# ── factory tests ──────────────────────────────────────────────────────


class TestSandboxAdapterFactory:
    def test_returns_adapter_based_on_planner(self, monkeypatch, tmp_path):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/bwrap" if cmd == "bwrap" else None)

        factory = SandboxAdapterFactory(tmp_path)
        adapter = factory.create()
        assert isinstance(adapter, LinuxBubblewrapAdapter)

    def test_fallback_to_noop(self, monkeypatch, tmp_path):
        monkeypatch.setattr("platform.system", lambda: "FreeBSD")
        monkeypatch.setattr("shutil.which", lambda cmd: None)

        factory = SandboxAdapterFactory(tmp_path)
        adapter = factory.create()
        assert isinstance(adapter, NoopSandboxAdapter)

    def test_create_plan_writes_audit(self, tmp_path, monkeypatch):
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))

        plan = SandboxAdapterFactory(tmp_path).create_plan(["pwd"], purpose="shell")
        assert plan.dry_run is True

        events = AuditLogger(tmp_path).read_recent(limit=5)
        sandbox_events = [e for e in events if e.type == "sandbox_plan_created"]
        assert len(sandbox_events) >= 1
        ev = sandbox_events[0]
        assert ev.metadata["backend"]
        assert ev.metadata["purpose"] == "shell"
        assert ev.metadata["dry_run"] == "true"

    def test_network_false_overrides_request(self, tmp_path):
        config = SafeCodeConfig()
        config.sandbox.network_enabled = False

        plan = SandboxAdapterFactory(tmp_path, config).create_plan(
            ["echo", "hello"],
            allow_network=True,
        )
        assert plan.network_enabled is False

    def test_env_values_not_exposed(self, tmp_path):
        plan = SandboxAdapterFactory(tmp_path).create_plan(
            ["echo", "hello"],
            env={"SECRET_TOKEN": "topsecret", "PATH": "/usr/bin"},
        )
        assert "topsecret" not in str(plan.env_keys)
        assert "SECRET_TOKEN" not in " ".join(plan.warnings)
        assert "SECRET_TOKEN" not in " ".join(plan.limitations)


class TestWritablePathsValidation:
    def test_project_root_escape_rejected(self, tmp_path):
        """writable_paths outside project root should be caught before plan."""
        factory = SandboxAdapterFactory(tmp_path)
        with pytest.raises(PermissionError, match="escapes project root"):
            factory.create_plan(
                ["echo", "hello"],
                writable_paths=[tmp_path.parent / "outside"],
            )

    def test_absolute_writable_paths_in_plan(self, tmp_path):
        factory = SandboxAdapterFactory(tmp_path)
        plan = factory.create_plan(
            ["echo", "hello"],
            writable_paths=[tmp_path / "data"],
        )
        assert str(tmp_path / "data") in plan.writable_paths

    def test_factory_blocks_non_allowlisted_command_and_audits(self, tmp_path, monkeypatch):
        """CommandPolicy enforcement lives in the factory, not only the CLI."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))

        with pytest.raises(PermissionError, match="not allowlisted"):
            SandboxAdapterFactory(tmp_path).create_plan(["curl", "https://example.com"])

        events = AuditLogger(tmp_path).read_recent(limit=5)
        blocked = [event for event in events if event.type == "sandbox_plan_blocked"]
        assert blocked
        assert blocked[0].metadata["command_head"] == "curl"


# ── command policy integration tests ───────────────────────────────────


class TestCommandPolicyIntegration:
    def test_high_risk_command_blocked(self, tmp_path, monkeypatch):
        """High-risk commands produce sandbox_plan_blocked audit event."""
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))

        from safecode.policy.commands import CommandPolicy
        from safecode.config import SafeCodeConfig

        config = SafeCodeConfig.load(tmp_path)
        decision = CommandPolicy(config).evaluate("rm -rf /tmp/safecode-test", approved=False)
        assert decision.allowed is False

    def test_non_allowlisted_command_blocked(self):
        from safecode.policy.commands import CommandPolicy
        from safecode.config import SafeCodeConfig

        decision = CommandPolicy(SafeCodeConfig()).evaluate("curl https://evil.com", approved=True)
        assert decision.allowed is False

    def test_allowlisted_low_risk_command_allowed(self):
        from safecode.policy.commands import CommandPolicy
        from safecode.config import SafeCodeConfig

        decision = CommandPolicy(SafeCodeConfig()).evaluate("pwd", approved=False)
        assert decision.allowed is True

    def test_factory_allows_medium_risk_dry_run_plan(self, tmp_path):
        """Dry-run planning can show medium-risk commands without executing them."""
        plan = SandboxAdapterFactory(tmp_path).create_plan(["git", "status"])
        assert plan.command == ["git", "status"]
        assert plan.dry_run is True


# ── regression: existing suites still pass ────────────────────────────


class TestExistingSuiteRegression:
    def test_sandbox_status_works(self, tmp_path, monkeypatch):
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))

        from safecode.sandbox.planner import SandboxPlanner
        plan = SandboxPlanner(tmp_path).plan()
        assert plan.recommended_backend is not None

    def test_existing_mcp_readonly_works(self, tmp_path, monkeypatch):
        from safecode.mcp.runner import MCPReadOnlyRunner
        import textwrap as tw

        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        server_path = tmp_path / "mock_server.py"
        server_path.write_text(
            tw.dedent("""import json, sys; p=json.loads(sys.stdin.read() or '{}'); print(json.dumps({"output":{"ok":True}}))"""),
            encoding="utf-8",
        )
        sac = tmp_path / ".sac"
        sac.mkdir()
        (sac / "mcp.toml").write_text(
            f'[servers.mock]\ncommand = "{shlex.join([sys.executable, str(server_path)])}"\nenabled = true\n',
            encoding="utf-8",
        )
        config = SafeCodeConfig()
        config.shell.allowed_commands = [sys.executable]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = True

        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})
        assert result.blocked is False
