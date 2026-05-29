"""Linux Bubblewrap argv plan tests for v1.7.2.

Verifies BubblewrapArgsBuilder generates conservative bwrap arguments
without executing bwrap.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.bubblewrap import BubblewrapArgsBuilder, BubblewrapArgsPlan
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability


def _make_request(**kwargs):
    defaults = {
        "command": ["echo", "hello"],
        "cwd": Path("/tmp/test_project"),
        "purpose": "shell",
        "allow_network": False,
        "readonly_filesystem": True,
        "writable_paths": [],
        "env": {},
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return SandboxExecutionRequest(**defaults)


def _make_bwrap_cap():
    return SandboxCapability(
        backend=SandboxBackend.LINUX_BUBBLEWRAP,
        available=True,
        supported_platforms=["Linux"],
        reason="test",
        limitations=["test limitation"],
    )


# ── BubblewrapArgsBuilder tests ───────────────────────────────────────


class TestBubblewrapArgsBuilder:
    def test_argv_starts_with_bwrap(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert plan.argv[0] == "bwrap"

    def test_includes_core_isolation_args(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "--die-with-parent" in plan.argv
        assert "--new-session" in plan.argv
        assert "--unshare-pid" in plan.argv
        assert "--unshare-ipc" in plan.argv
        assert "--unshare-uts" in plan.argv

    def test_network_disabled_includes_unshare_net(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(allow_network=False)
        )
        assert "--unshare-net" in plan.argv

    def test_network_enabled_no_unshare_net_with_warning(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(allow_network=True)
        )
        assert "--unshare-net" not in plan.argv
        assert any("v1.7.2" in w for w in plan.warnings)

    def test_project_root_ro_bind(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert str(tmp_path) in plan.bind_readonly_paths
        assert "--ro-bind" in plan.argv

    def test_readonly_filesystem_no_writable_bind(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=True)
        )
        assert len(plan.bind_writable_paths) == 0

    def test_writable_inside_project_allows_bind(self, tmp_path):
        writable = tmp_path / "output"
        writable.mkdir()
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[writable])
        )
        assert str(writable) in plan.bind_writable_paths
        assert "--bind" in plan.argv

    def test_writable_outside_project_rejected(self, tmp_path):
        outside = tmp_path.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[outside])
        )
        assert str(outside) not in plan.bind_writable_paths

    def test_sensitive_writable_path_not_in_bind(self, tmp_path):
        sensitive_file = tmp_path / "secret.pem"
        sensitive_file.write_text("private", encoding="utf-8")
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[sensitive_file])
        )
        assert str(sensitive_file) not in plan.bind_writable_paths

    def test_blocked_writable_roots_not_bound(self, tmp_path):
        """Verify /home, /tmp, /var, /private are not writable-bound."""
        for blocked in ["/home", "/tmp", "/var", "/private"]:
            bp = Path(blocked) / "sub"
            config = SafeCodeConfig()
            builder = BubblewrapArgsBuilder(Path("/tmp/test_project"), config)
            plan = builder.build(
                _make_request(readonly_filesystem=False, writable_paths=[bp])
            )
            assert str(bp) not in plan.bind_writable_paths

    def test_tmpfs_includes_tmp(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "/tmp" in plan.tmpfs_paths
        assert "--tmpfs" in plan.argv
        assert "/tmp" in plan.argv

    def test_command_appended_after_double_dash(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "--" in plan.argv
        dd_idx = plan.argv.index("--")
        assert plan.argv[dd_idx + 1 :] == ["echo", "hello"]

    def test_env_values_not_in_argv(self, tmp_path):
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(env={"API_KEY": "supersecret", "HOME": "/home"})
        )
        assert "supersecret" not in " ".join(plan.argv)
        assert "supersecret" not in " ".join(plan.warnings)


# ── adapter integration tests ─────────────────────────────────────────


class TestAdapterArgsIntegration:
    def test_linux_adapter_fills_args_preview(self, tmp_path):
        cap = _make_bwrap_cap()
        adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(cwd=tmp_path))
        assert len(plan.args_preview) > 0
        assert plan.args_backend == "linux_bubblewrap"
        assert plan.args_preview[0] == "bwrap"

    def test_linux_adapter_respects_config_network_disabled(self, tmp_path):
        cap = _make_bwrap_cap()
        config = SafeCodeConfig()
        config.sandbox.network_enabled = False
        adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path, config=config)

        plan = adapter.build_plan(_make_request(cwd=tmp_path, allow_network=True))

        assert plan.network_enabled is False
        assert "--unshare-net" in plan.args_preview
        assert any("Network access was requested" in warning for warning in plan.warnings)

    def test_noop_adapter_no_args_preview(self):
        plan = NoopSandboxAdapter().build_plan(_make_request())
        assert len(plan.args_preview) == 0
        assert plan.args_backend is None

    def test_macos_adapter_no_args_preview(self, tmp_path):
        cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["macOS"],
            reason="test",
        )
        adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(cwd=tmp_path))
        assert len(plan.args_preview) == 0

    def test_docker_adapter_no_args_preview(self):
        cap = SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=True,
            supported_platforms=["all"],
            reason="test",
        )
        plan = DockerSandboxAdapter(cap).build_plan(_make_request())
        assert len(plan.args_preview) == 0

    def test_adapter_no_subprocess(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        cap = _make_bwrap_cap()
        LinuxBubblewrapAdapter(cap, project_root=tmp_path, config=SafeCodeConfig()).build_plan(
            _make_request(cwd=tmp_path)
        )
        assert len(called) == 0


# ── regression tests ──────────────────────────────────────────────────


class TestExistingSuiteRegression:
    def test_sandbox_plan_works(self, tmp_path):
        from safecode.sandbox.factory import SandboxAdapterFactory
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True

    def test_mcp_readonly_still_works(self, tmp_path, monkeypatch):
        from safecode.mcp.runner import MCPReadOnlyRunner
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        server_path = tmp_path / "mock_server.py"
        server_path.write_text(
            "import json,sys\np=json.loads(sys.stdin.read() or '{}')\nprint(json.dumps({'output':{'ok':True}}))",
            encoding="utf-8",
        )
        (tmp_path / ".sac").mkdir()
        (tmp_path / ".sac" / "mcp.toml").write_text(
            f'[servers.mock]\ncommand = "{shlex.join([sys.executable, str(server_path)])}"\nenabled = true\n',
            encoding="utf-8",
        )
        config = SafeCodeConfig()
        config.shell.allowed_commands = [sys.executable]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = True
        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})
        assert result.blocked is False
