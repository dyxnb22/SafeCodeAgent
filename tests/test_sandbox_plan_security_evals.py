"""Sandbox plan security eval suite for v1.7.4.

Cross-backend security tests verifying that every sandbox backend preview
satisfies: no execution, no env/secret leaks, no path escapes, no sensitive
path writes, network policy consistency, and backend isolation.

This complements backend-specific test files with cross-cutting security checks.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.cli import app
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.bubblewrap import BubblewrapArgsBuilder
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.docker import DockerContainerPlanBuilder
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.seatbelt import SeatbeltProfileBuilder

runner = CliRunner()


# ── helpers ───────────────────────────────────────────────────────────

def _request(**kwargs):
    d = {
        "command": ["echo", "hello"],
        "cwd": Path("/tmp/testproj"),
        "purpose": "shell",
        "allow_network": False,
        "readonly_filesystem": True,
        "writable_paths": [],
        "env": {},
        "timeout_seconds": 30,
    }
    d.update(kwargs)
    return SandboxExecutionRequest(**d)


def _cfg(**kwargs):
    c = SafeCodeConfig()
    for k, v in kwargs.items():
        setattr(c.sandbox, k, v)
    return c


def _cap(backend):
    return SandboxCapability(backend=backend, available=True, supported_platforms=["test"], reason="test")


def _no_subprocess(monkeypatch):
    called = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
    monkeypatch.setattr(subprocess, "call", lambda *a, **kw: called.append(1))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))
    return called


def _strings(obj) -> str:
    """Flatten all string content from an object for secret leak checks."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (list, tuple)):
        return " ".join(str(x) for x in obj)
    if hasattr(obj, "__dict__"):
        return " ".join(str(v) for v in vars(obj).values())
    return str(obj)


# ── Category 1: No execution guarantee ────────────────────────────────


class TestNoExecutionGuarantee:
    def test_seatbelt_builder_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        SeatbeltProfileBuilder(tmp_path, _cfg()).build(_request())
        assert len(c) == 0

    def test_bubblewrap_builder_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        BubblewrapArgsBuilder(tmp_path, _cfg()).build(_request())
        assert len(c) == 0

    def test_docker_builder_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        DockerContainerPlanBuilder(tmp_path, _cfg()).build(_request())
        assert len(c) == 0

    def test_macos_adapter_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        MacOSSeatbeltAdapter(_cap(SandboxBackend.MACOS_SEATBELT), tmp_path, _cfg()).build_plan(
            _request(cwd=tmp_path)
        )
        assert len(c) == 0

    def test_linux_adapter_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        LinuxBubblewrapAdapter(_cap(SandboxBackend.LINUX_BUBBLEWRAP), tmp_path, _cfg()).build_plan(
            _request(cwd=tmp_path)
        )
        assert len(c) == 0

    def test_docker_adapter_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        DockerSandboxAdapter(_cap(SandboxBackend.DOCKER), tmp_path, _cfg()).build_plan(
            _request(cwd=tmp_path)
        )
        assert len(c) == 0

    def test_factory_create_plan_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["echo", "hello"])
        assert len(c) == 0

    def test_cli_sandbox_plan_no_subprocess(self, monkeypatch, tmp_path):
        c = _no_subprocess(monkeypatch)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sandbox", "plan", "git", "status"])
        assert result.exit_code == 0
        assert "This command was NOT executed" in result.output
        assert len(c) == 0


# ── Category 2: Network policy consistency ────────────────────────────


class TestNetworkPolicyConsistency:
    def test_macos_profile_no_network_when_disabled(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, _cfg(network_enabled=False)).build(_request(allow_network=False))
        assert "network-outbound" not in plan.profile_text

    def test_bubblewrap_unshare_net_when_disabled(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, _cfg(network_enabled=False)).build(_request(allow_network=False))
        assert "--unshare-net" in plan.argv

    def test_docker_network_none_when_disabled(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, _cfg(network_enabled=False)).build(_request(allow_network=False))
        args = " ".join(plan.argv)
        assert "--network none" in args or ("--network" in plan.argv and "none" in plan.argv)

    def test_request_network_overridden_by_config_all_three(self, tmp_path):
        """All three backends force network off when config disables it."""
        cfg = _cfg(network_enabled=False)
        req = _request(allow_network=True, cwd=tmp_path)
        m = MacOSSeatbeltAdapter(_cap(SandboxBackend.MACOS_SEATBELT), tmp_path, cfg).build_plan(req)
        l = LinuxBubblewrapAdapter(_cap(SandboxBackend.LINUX_BUBBLEWRAP), tmp_path, cfg).build_plan(req)
        d = DockerSandboxAdapter(_cap(SandboxBackend.DOCKER), tmp_path, cfg).build_plan(req)
        assert m.network_enabled is False
        assert l.network_enabled is False
        assert d.network_enabled is False

    def test_network_enabled_produces_warning_all_three(self, tmp_path):
        """All three backends warn when network is enabled in preview."""
        cfg = _cfg(network_enabled=True)
        req = _request(allow_network=True, cwd=tmp_path)
        m = MacOSSeatbeltAdapter(_cap(SandboxBackend.MACOS_SEATBELT), tmp_path, cfg).build_plan(req)
        l = LinuxBubblewrapAdapter(_cap(SandboxBackend.LINUX_BUBBLEWRAP), tmp_path, cfg).build_plan(req)
        d = DockerSandboxAdapter(_cap(SandboxBackend.DOCKER), tmp_path, cfg).build_plan(req)
        assert any("not validated" in w.lower() or "v1.7" in w for w in m.profile_warnings)
        assert any("not validated" in w.lower() or "v1.7" in w for w in l.args_warnings)
        assert any("not validated" in w.lower() or "v1.7" in w for w in d.container_warnings)


# ── Category 3: Filesystem boundary consistency ───────────────────────


class TestFilesystemBoundaryConsistency:
    def test_outside_writable_rejected_macos(self, tmp_path):
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        plan = SeatbeltProfileBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[outside])
        )
        assert str(outside) not in plan.allowed_write_paths

    def test_outside_writable_rejected_bubblewrap(self, tmp_path):
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        plan = BubblewrapArgsBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[outside])
        )
        assert str(outside) not in plan.bind_writable_paths

    def test_outside_writable_rejected_docker(self, tmp_path):
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        plan = DockerContainerPlanBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[outside])
        )
        assert str(outside) not in plan.writable_mounts

    def test_factory_rejects_outside_writable(self, tmp_path):
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        with pytest.raises(PermissionError, match="escapes"):
            SandboxAdapterFactory(tmp_path, _cfg()).create_plan(
                ["echo", "hello"], writable_paths=[outside]
            )

    def test_symlink_to_outside_not_writable_in_any_backend(self, tmp_path):
        outside = tmp_path.parent / "outside-target"
        outside.mkdir(exist_ok=True)
        link = tmp_path / "outside-link"
        link.symlink_to(outside, target_is_directory=True)

        macos = SeatbeltProfileBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[link])
        )
        linux = BubblewrapArgsBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[link])
        )
        docker = DockerContainerPlanBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[link])
        )

        assert str(link) not in macos.allowed_write_paths
        assert str(link) not in linux.bind_writable_paths
        assert str(link) not in docker.writable_mounts

    def test_project_root_read_only_in_all_three(self, tmp_path):
        req = _request(cwd=tmp_path)
        m = SeatbeltProfileBuilder(tmp_path, _cfg()).build(req)
        l = BubblewrapArgsBuilder(tmp_path, _cfg()).build(req)
        d = DockerContainerPlanBuilder(tmp_path, _cfg()).build(req)
        assert str(tmp_path) in m.allowed_read_paths
        assert str(tmp_path) in l.bind_readonly_paths
        assert str(tmp_path) in d.readonly_mounts

    def test_blocked_roots_not_in_any_write_target(self, tmp_path):
        for builder_cls in [SeatbeltProfileBuilder, BubblewrapArgsBuilder, DockerContainerPlanBuilder]:
            builder = builder_cls(tmp_path, _cfg())
            plan = builder.build(
                _request(readonly_filesystem=False, writable_paths=[Path("/home/user"), Path("/tmp/dir")])
            )
            s = _strings(plan)
            assert "/home" not in s or "block" in s.lower()


# ── Category 4: Sensitive path consistency ────────────────────────────


class TestSensitivePathConsistency:
    def test_dotenv_not_in_write_allow_macos(self, tmp_path):
        p = tmp_path / ".env"
        p.touch()
        plan = SeatbeltProfileBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        assert str(p) not in plan.allowed_write_paths

    def test_dotenv_not_in_bind_bubblewrap(self, tmp_path):
        p = tmp_path / ".env"
        p.touch()
        plan = BubblewrapArgsBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        assert str(p) not in plan.bind_writable_paths

    def test_dotenv_not_in_mount_docker(self, tmp_path):
        p = tmp_path / ".env"
        p.touch()
        plan = DockerContainerPlanBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        assert str(p) not in plan.writable_mounts

    def test_secret_pem_not_in_any_write_allow(self, tmp_path):
        p = tmp_path / "secret.pem"
        p.touch()
        macos = SeatbeltProfileBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        linux = BubblewrapArgsBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        docker = DockerContainerPlanBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        assert str(p) not in macos.allowed_write_paths
        assert str(p) not in linux.bind_writable_paths
        assert str(p) not in docker.writable_mounts

    def test_credentials_not_in_any_write_allow(self, tmp_path):
        p = tmp_path / "credentials.json"
        p.touch()
        macos = SeatbeltProfileBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        linux = BubblewrapArgsBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        docker = DockerContainerPlanBuilder(tmp_path, _cfg()).build(
            _request(readonly_filesystem=False, writable_paths=[p])
        )
        assert str(p) not in macos.allowed_write_paths
        assert str(p) not in linux.bind_writable_paths
        assert str(p) not in docker.writable_mounts

    def test_env_values_not_in_any_backend_output(self, tmp_path):
        """No backend preview exposes env values in any output string."""
        env = {"SECRET_TOKEN": "abc123xyz", "HOME": "/home"}
        req = _request(cwd=tmp_path, env=env)
        for builder_cls in [SeatbeltProfileBuilder, BubblewrapArgsBuilder, DockerContainerPlanBuilder]:
            builder = builder_cls(tmp_path, _cfg())
            plan = builder.build(req)
            s = _strings(plan)
            assert "abc123xyz" not in s

    def test_env_value_not_in_plan_strings(self, tmp_path):
        req = _request(cwd=tmp_path, env={"API_KEY": "topsecret"})
        for adapter_cls, backend in [
            (MacOSSeatbeltAdapter, SandboxBackend.MACOS_SEATBELT),
            (LinuxBubblewrapAdapter, SandboxBackend.LINUX_BUBBLEWRAP),
            (DockerSandboxAdapter, SandboxBackend.DOCKER),
        ]:
            plan = adapter_cls(_cap(backend), tmp_path, _cfg()).build_plan(req)
            s = _strings(plan)
            assert "topsecret" not in s


# ── Category 5: Command policy and audit ──────────────────────────────


class TestCommandPolicyAndAudit:
    def test_high_risk_blocked_writes_audit(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        with pytest.raises(PermissionError):
            SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["rm", "-rf", "/tmp"])
        events = AuditLogger(tmp_path).read_recent(limit=5)
        blocked = [e for e in events if e.type == "sandbox_plan_blocked"]
        assert len(blocked) >= 1

    def test_non_allowlisted_blocked(self, tmp_path):
        with pytest.raises(PermissionError):
            SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["curl", "https://example.com"])

    def test_low_risk_allowed(self, tmp_path):
        plan = SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["echo", "hello"])
        assert plan.dry_run is True

    def test_git_status_medium_risk_allowed_for_dry_run_plan(self, tmp_path):
        plan = SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["git", "status"])
        assert plan.command == ["git", "status"]
        assert plan.dry_run is True

    def test_blocked_audit_metadata_no_full_args(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        try:
            SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["rm", "-rf", "/tmp"])
        except PermissionError:
            pass
        events = AuditLogger(tmp_path).read_recent(limit=5)
        blocked = [e for e in events if e.type == "sandbox_plan_blocked"]
        if blocked:
            md = blocked[0].metadata
            assert md.get("command_head") == "rm"
            assert "/tmp" not in str(md)

    def test_created_audit_metadata_no_env_values(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        SandboxAdapterFactory(tmp_path, _cfg()).create_plan(
            ["echo", "hello"], env={"SECRET": "xyz"}
        )
        events = AuditLogger(tmp_path).read_recent(limit=5)
        created = [e for e in events if e.type == "sandbox_plan_created"]
        assert len(created) >= 1
        assert "xyz" not in str(created[0].metadata)

    def test_dry_run_metadata_is_true(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["echo", "hello"])
        events = AuditLogger(tmp_path).read_recent(limit=5)
        created = [e for e in events if e.type == "sandbox_plan_created"]
        assert len(created) >= 1
        assert created[0].metadata.get("dry_run") == "true"


# ── Category 6: Backend isolation ─────────────────────────────────────


class TestBackendIsolation:
    def test_macos_only_fills_profile_preview(self, tmp_path):
        plan = MacOSSeatbeltAdapter(_cap(SandboxBackend.MACOS_SEATBELT), tmp_path, _cfg()).build_plan(
            _request(cwd=tmp_path)
        )
        assert plan.profile_preview is not None
        assert len(plan.args_preview) == 0
        assert len(plan.container_preview) == 0

    def test_linux_only_fills_args_preview(self, tmp_path):
        plan = LinuxBubblewrapAdapter(_cap(SandboxBackend.LINUX_BUBBLEWRAP), tmp_path, _cfg()).build_plan(
            _request(cwd=tmp_path)
        )
        assert len(plan.args_preview) > 0
        assert plan.profile_preview is None
        assert len(plan.container_preview) == 0

    def test_docker_only_fills_container_preview(self, tmp_path):
        plan = DockerSandboxAdapter(_cap(SandboxBackend.DOCKER), tmp_path, _cfg()).build_plan(
            _request(cwd=tmp_path)
        )
        assert len(plan.container_preview) > 0
        assert plan.profile_preview is None
        assert len(plan.args_preview) == 0

    def test_noop_all_three_empty(self):
        plan = NoopSandboxAdapter().build_plan(_request())
        assert plan.profile_preview is None
        assert len(plan.args_preview) == 0
        assert len(plan.container_preview) == 0

    def test_os_adapters_supports_execution_false(self):
        # v1.8.0: Noop adapter now supports execution (local policy-gated).
        # macOS/Linux/Docker backends remain dry-run only.
        for adapter in [
            MacOSSeatbeltAdapter(_cap(SandboxBackend.MACOS_SEATBELT)),
            LinuxBubblewrapAdapter(_cap(SandboxBackend.LINUX_BUBBLEWRAP)),
            DockerSandboxAdapter(_cap(SandboxBackend.DOCKER)),
        ]:
            assert adapter.supports_execution() is False
        assert NoopSandboxAdapter().supports_execution() is True


# ── regression ────────────────────────────────────────────────────────


class TestExistingSuiteRegression:
    def test_factory_plan_works(self, tmp_path):
        plan = SandboxAdapterFactory(tmp_path, _cfg()).create_plan(["echo", "hello"])
        assert plan.dry_run is True

    def test_mcp_readonly_works(self, tmp_path, monkeypatch):
        from safecode.mcp.runner import MCPReadOnlyRunner
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        sp = tmp_path / "mock_server.py"
        sp.write_text(
            "import json,sys\np=json.loads(sys.stdin.read() or '{}')\nprint(json.dumps({'output':{'ok':True}}))",
            encoding="utf-8",
        )
        (tmp_path / ".sac").mkdir()
        (tmp_path / ".sac" / "mcp.toml").write_text(
            f'[servers.mock]\ncommand = "{shlex.join([sys.executable, str(sp)])}"\nenabled = true\n',
            encoding="utf-8",
        )
        c = _cfg()
        c.shell.allowed_commands = [sys.executable]
        c.shell.require_confirm_for_medium = False
        c.sandbox.network_enabled = True
        r = MCPReadOnlyRunner(tmp_path, c).call_readonly("mock", "mock.list", {})
        assert r.blocked is False
