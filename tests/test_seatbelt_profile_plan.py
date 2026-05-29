"""macOS Seatbelt profile plan tests for v1.7.1.

Verifies SeatbeltProfileBuilder generates conservative .sb profiles
without executing sandbox-exec.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.seatbelt import SeatbeltProfileBuilder, SeatbeltProfilePlan


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


def _make_seatbelt_cap():
    return SandboxCapability(
        backend=SandboxBackend.MACOS_SEATBELT,
        available=True,
        supported_platforms=["macOS"],
        reason="test",
        limitations=["test limitation"],
    )


# ── SeatbeltProfileBuilder tests ──────────────────────────────────────


class TestSeatbeltProfileBuilder:
    def test_generates_deny_default(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "(deny default)" in plan.profile_text
        assert "(version 1)" in plan.profile_text

    def test_allows_read_of_project_root(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert f'(allow file-read* (subpath "{tmp_path}"))' in plan.profile_text

    def test_readonly_filesystem_no_write_allow(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=True)
        )
        assert len(plan.allowed_write_paths) == 0

    def test_writable_inside_project_allows_write(self, tmp_path):
        writable = tmp_path / "output"
        writable.mkdir()
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[writable])
        )
        assert f'(allow file-write* (subpath "{writable}"))' in plan.profile_text

    def test_writable_outside_project_rejected(self, tmp_path):
        outside = tmp_path.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[outside])
        )
        assert str(outside) not in plan.allowed_write_paths

    def test_sensitive_names_in_denied_paths(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert any(".env" in d for d in plan.denied_paths)
        assert any(".ssh" in d for d in plan.denied_paths)

    def test_sensitive_writable_path_is_not_allowed(self, tmp_path):
        sensitive_file = tmp_path / "secret.pem"
        sensitive_file.write_text("private", encoding="utf-8")
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[sensitive_file])
        )
        assert str(sensitive_file) not in plan.allowed_write_paths
        assert str(sensitive_file) not in plan.profile_text
        assert any("sensitive path segment" in warning for warning in plan.warnings)

    def test_profile_paths_escape_double_quotes(self, tmp_path):
        quoted = tmp_path / 'quoted"name'
        quoted.mkdir()
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[quoted])
        )
        assert 'quoted\\"name' in plan.profile_text

    def test_network_disabled_no_network_in_profile(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(allow_network=False)
        )
        assert "network-outbound" not in plan.profile_text
        assert "DISABLED" in plan.profile_text

    def test_network_enabled_produces_profile_with_warning(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(allow_network=True)
        )
        assert "(allow network-outbound)" in plan.profile_text
        assert any("v1.7.1" in w for w in plan.warnings)

    def test_env_values_not_in_profile_or_plan(self, tmp_path):
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(env={"API_KEY": "supersecret", "HOME": "/home"})
        )
        assert "supersecret" not in plan.profile_text
        assert "supersecret" not in str(plan.allowed_read_paths)
        assert "supersecret" not in str(plan.allowed_write_paths)


# ── adapter integration tests ─────────────────────────────────────────


class TestAdapterProfileIntegration:
    def test_macos_adapter_fills_profile_preview(self, tmp_path):
        cap = _make_seatbelt_cap()
        adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(cwd=tmp_path))
        assert plan.profile_preview is not None
        assert plan.profile_backend == "macos_seatbelt"
        assert "(deny default)" in plan.profile_preview

    def test_macos_adapter_respects_config_network_disabled(self, tmp_path):
        cap = _make_seatbelt_cap()
        config = SafeCodeConfig()
        config.sandbox.network_enabled = False
        adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=config)

        plan = adapter.build_plan(_make_request(cwd=tmp_path, allow_network=True))

        assert plan.network_enabled is False
        assert plan.profile_preview is not None
        assert "network-outbound" not in plan.profile_preview
        assert any("Network access was requested" in warning for warning in plan.warnings)

    def test_macos_adapter_plan_writable_paths_match_profile(self, tmp_path):
        cap = _make_seatbelt_cap()
        adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        safe_path = tmp_path / "safe-output"
        safe_path.mkdir()
        sensitive_path = tmp_path / "secret.pem"
        sensitive_path.write_text("private", encoding="utf-8")

        plan = adapter.build_plan(
            _make_request(
                cwd=tmp_path,
                readonly_filesystem=False,
                writable_paths=[safe_path, sensitive_path],
            )
        )

        assert str(safe_path) in plan.writable_paths
        assert str(sensitive_path) not in plan.writable_paths

    def test_noop_adapter_no_profile_preview(self):
        plan = NoopSandboxAdapter().build_plan(_make_request())
        assert plan.profile_preview is None
        assert plan.profile_backend is None

    def test_linux_adapter_no_profile_preview(self):
        cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["Linux"],
            reason="test",
        )
        plan = LinuxBubblewrapAdapter(cap).build_plan(_make_request())
        assert plan.profile_preview is None

    def test_docker_adapter_no_profile_preview(self):
        cap = SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=True,
            supported_platforms=["all"],
            reason="test",
        )
        plan = DockerSandboxAdapter(cap).build_plan(_make_request())
        assert plan.profile_preview is None

    def test_adapter_no_subprocess(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        cap = _make_seatbelt_cap()
        MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=SafeCodeConfig()).build_plan(
            _make_request(cwd=tmp_path)
        )
        assert len(called) == 0


# ── regression tests ──────────────────────────────────────────────────


class TestExistingSuiteRegression:
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

    def test_sandbox_plan_works(self, tmp_path):
        from safecode.sandbox.factory import SandboxAdapterFactory
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True
