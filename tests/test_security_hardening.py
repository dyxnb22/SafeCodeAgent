from pathlib import Path
import json
import shlex
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone

from safecode.config import SafeCodeConfig, merge_trusted_config
from safecode.checkpoint.manager import CheckpointManager
from safecode.context.collector import ContextCollector
from safecode.agent.orchestrator import AgentOrchestrator
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.hooks.approvals import HookApprovalStore
from safecode.hooks.runner import HookRunner
from safecode.llm.factory import create_llm_client
from safecode.llm.mock import MockLLMClient
from safecode.logs.runtime import RuntimeLogger
from safecode.mcp.discovery import MCPDiscovery
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.mcp.proposal import MCPWriteProposalStore
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.patch.applier import PatchApplier
from safecode.policy.commands import CommandPolicy
from safecode.patch.validator import PatchValidationError, PatchValidator
from safecode.shell.risk import RiskLevel, ShellRiskClassifier
from safecode.shell.runner import ShellRunner
import safecode.hooks.approvals as approvals


def future_timestamp() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")


def external_approval_dir(tmp_path: Path) -> Path:
    return tmp_path.parent / f"approvals-{tmp_path.name}"


def write_mock_mcp_server(tmp_path: Path) -> Path:
    path = tmp_path / "mock_mcp_server.py"
    path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            payload = json.loads(sys.stdin.read() or "{}")
            tool = payload.get("tool", "")
            input_data = payload.get("input", {})

            if tool.endswith("secret"):
                output = "API_KEY=abc123"
            elif tool.endswith("large"):
                size = 0
                if isinstance(input_data, dict):
                    size = int(input_data.get("size", 0))
                output = "A" * size
            else:
                output = {"ok": True, "input": input_data}

            print(json.dumps({"output": output}))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def write_mcp_config(tmp_path: Path, command: str) -> None:
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


def test_high_risk_command_is_blocked_even_when_approved(tmp_path: Path) -> None:
    result = ShellRunner(tmp_path).run("rm -rf /tmp/safecode-example", approved=True)

    assert result.executed is False
    assert result.exit_code == 126


def test_shell_operator_is_high_risk(tmp_path: Path) -> None:
    risk = ShellRiskClassifier().classify("echo hello && rm -rf /tmp/example")

    assert risk.level == RiskLevel.HIGH
    assert any("shell operator" in reason for reason in risk.reasons)


def test_shell_runner_uses_argv_execution(tmp_path: Path) -> None:
    result = ShellRunner(tmp_path).run("echo hello", approved=False)

    assert result.executed is True
    assert result.stdout.strip() == "hello"


def test_shell_runner_sanitizes_git_env_vars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "alias.pwn=!sh")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "alias.pwn")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "!sh")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/tmp/global")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/tmp/system")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_DIR", "/tmp/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/tmp/work")
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -oProxyCommand=evil")
    monkeypatch.setenv("GIT_ASKPASS", "/tmp/askpass")
    monkeypatch.setenv("SSH_ASKPASS", "/tmp/ssh-askpass")
    monkeypatch.setenv("GIT_PAGER", "less")
    monkeypatch.setenv("GIT_EDITOR", "vi")
    monkeypatch.setenv("GIT_SEQUENCE_EDITOR", "vi")
    monkeypatch.setenv("GIT_SSH", "/tmp/ssh")
    monkeypatch.setenv("PAGER", "less")
    monkeypatch.setenv("LESS", "-R")

    def fake_run(args, cwd, text, capture_output, env, timeout, check):
        assert "GIT_CONFIG_PARAMETERS" not in env
        assert "GIT_CONFIG_COUNT" not in env
        assert "GIT_CONFIG_GLOBAL" not in env
        assert "GIT_CONFIG_SYSTEM" not in env
        assert "GIT_CONFIG_NOSYSTEM" not in env
        assert "GIT_DIR" not in env
        assert "GIT_WORK_TREE" not in env
        assert "GIT_SSH_COMMAND" not in env
        assert "GIT_ASKPASS" not in env
        assert "SSH_ASKPASS" not in env
        assert "GIT_PAGER" not in env
        assert "GIT_EDITOR" not in env
        assert "GIT_SEQUENCE_EDITOR" not in env
        assert "GIT_SSH" not in env
        assert "PAGER" not in env
        assert "LESS" not in env
        assert not any(key.startswith("GIT_CONFIG_KEY_") for key in env)
        assert not any(key.startswith("GIT_CONFIG_VALUE_") for key in env)
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = ShellRunner(tmp_path).run("echo ok", approved=False)

    assert result.executed is True
    assert result.stdout.strip() == "ok"


def test_shell_runner_blocks_network_commands_when_disabled(tmp_path: Path) -> None:
    config = SafeCodeConfig()
    config.shell.allowed_commands = ["git", "curl", "npm", "pip", "npx"]
    runner = ShellRunner(tmp_path, config)

    for command in [
        "git fetch",
        "git clone https://example.com/repo.git",
        "curl https://example.com",
        "npm install lodash",
        "pip install requests",
        "npx cowsay",
    ]:
        result = runner.run(command, approved=True)
        assert result.executed is False
        assert result.exit_code == 126

    assert "Network access is disabled" in runner.run("curl https://example.com", approved=True).stderr
    assert "Network access is disabled" in runner.run("npm install lodash", approved=True).stderr


def test_shell_runner_enforces_network_allowlist(tmp_path: Path, monkeypatch) -> None:
    config = SafeCodeConfig()
    config.sandbox.network_enabled = True
    config.sandbox.network_allowlist = ["example.com"]
    config.shell.allowed_commands = ["curl"]

    def fake_run(args, cwd, text, capture_output, env, timeout, check):
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = ShellRunner(tmp_path, config)
    result = runner.run("curl https://example.com", approved=True)

    assert result.executed is True
    assert result.stdout.strip() == "ok"

    blocked = runner.run("curl https://bad.com", approved=True)
    assert blocked.executed is False
    assert "not allowlisted" in blocked.stderr


def test_project_config_cannot_lower_user_security() -> None:
    user = SafeCodeConfig(policy="strict")
    project = SafeCodeConfig(policy="learning")
    project.shell.block_high_risk = False
    project.shell.require_confirm_for_medium = False
    project.sandbox.network_enabled = True

    merged = merge_trusted_config(user, project)

    assert merged.policy == "strict"
    assert merged.shell.block_high_risk is True
    assert merged.shell.require_confirm_for_medium is True
    assert merged.sandbox.network_enabled is False


def test_patch_validator_uses_sandbox_boundary(tmp_path: Path) -> None:
    proposal = PatchProposal(
        id="patch-test",
        task="escape",
        blocks=[PatchBlock(operation="update", file_path=Path("../outside.txt"), search="a", replace="b")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    try:
        PatchValidator(tmp_path).validate(proposal)
    except PatchValidationError as exc:
        assert "escapes project root" in str(exc)
    else:
        raise AssertionError("Path escape should be rejected.")


def test_mcp_write_operations_are_disabled(tmp_path: Path) -> None:
    try:
        MCPDiscovery(tmp_path).assert_write_allowed()
    except PermissionError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("MCP writes should be rejected by default.")


def test_mcp_readonly_call_succeeds_and_audited(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    result = runner.call_readonly("mock", "mock.list", {"query": "hello"})

    assert result.blocked is False
    assert result.exit_code == 0
    assert "ok" in result.output

    events = AuditLogger(tmp_path, config).read_recent(limit=10)
    event_types = [event.type for event in events]
    assert "mcp_call_proposed" in event_types
    assert "mcp_call_started" in event_types
    assert "mcp_call_completed" in event_types


def test_mcp_write_tool_is_blocked(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.write", {})

    assert result.blocked is True
    assert result.executed is False
    assert result.exit_code == 126

    events = AuditLogger(tmp_path, config).read_recent(limit=5)
    assert any(event.type == "mcp_call_blocked" for event in events)


def test_mcp_network_disabled_blocks_call(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = False

    result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})

    assert result.blocked is True
    assert "Network access is disabled" in result.error


def test_mcp_output_redaction_applies(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.get_secret", {})

    assert result.blocked is False
    assert "abc123" not in result.output
    assert "[REDACTED]" in result.output


def test_mcp_output_size_limit_is_enforced(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.max_context_chars = 50
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.get_large", {"size": 200})

    assert result.blocked is True
    assert "size limits" in result.error


def test_mcp_runner_sanitizes_git_env_vars(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -oProxyCommand=evil")
    monkeypatch.setenv("GIT_ASKPASS", "/tmp/askpass")
    monkeypatch.setenv("SSH_ASKPASS", "/tmp/ssh-askpass")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "alias.pwn=!sh")
    write_mcp_config(tmp_path, "echo ok")
    config = SafeCodeConfig()
    config.sandbox.network_enabled = True

    def fake_run(args, cwd, text, input, capture_output, env, timeout, check):
        assert "GIT_SSH_COMMAND" not in env
        assert "GIT_ASKPASS" not in env
        assert "SSH_ASKPASS" not in env
        assert "GIT_CONFIG_PARAMETERS" not in env
        return subprocess.CompletedProcess(args, 0, stdout='{"output":"ok"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})

    assert result.executed is True
    assert result.output == "ok"


def test_llm_factory_defaults_to_mock() -> None:
    client = create_llm_client(SafeCodeConfig())

    assert isinstance(client, MockLLMClient)


def test_project_config_cannot_force_real_llm_provider() -> None:
    user = SafeCodeConfig()
    project = SafeCodeConfig()
    project.llm.provider = "openai"

    merged = merge_trusted_config(user, project)

    assert merged.llm.provider == "mock"


def test_real_llm_requires_network_policy(monkeypatch) -> None:
    config = SafeCodeConfig()
    config.llm.provider = "openai"
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    try:
        create_llm_client(config)
    except PermissionError as exc:
        assert "Network access is disabled" in str(exc)
    else:
        raise AssertionError("Real LLM should require network policy.")


def test_hook_injection_is_blocked_by_shell_policy(tmp_path: Path) -> None:
    config = SafeCodeConfig()
    config.hooks.after_apply = ["rm -rf /tmp/safecode-hook-example"]

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 126


def test_medium_risk_hook_is_not_auto_approved(tmp_path: Path) -> None:
    config = SafeCodeConfig()
    config.hooks.after_apply = ["python -c 'print(1)'"]

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 126


def test_hook_runner_writes_audit_chain(tmp_path: Path) -> None:
    config = SafeCodeConfig()
    config.hooks.after_apply = ["python -c 'print(1)'"]

    HookRunner(tmp_path, config).run_after_apply()
    events = AgentOrchestrator(tmp_path).history(limit=5)
    event_types = [event.type for event in events]

    assert "hook_proposed" in event_types
    assert "hook_completed" in event_types
    assert events[-1].command == "python -c 'print(1)'"


def test_medium_hook_requires_persisted_approval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = True

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_approved_hook_uses_persisted_approval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = True
    HookApprovalStore(tmp_path, config).approve("after_apply", "git status")

    summary = HookRunner(tmp_path, config).run_after_apply()
    events = AgentOrchestrator(tmp_path).history(limit=5)
    event_types = [event.type for event in events]

    assert summary.results[0].executed is True
    assert "hook_approval_used" in event_types


def test_project_seeded_hook_approval_is_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = True
    project_store = tmp_path / ".sac" / "approvals"
    project_store.mkdir(parents=True)
    (project_store / "hooks.jsonl").write_text('{"command":"git status"}\n', encoding="utf-8")

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_hook_approval_dir_rejects_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / ".sac" / "approvals"))
    try:
        HookApprovalStore(tmp_path, SafeCodeConfig())
    except PermissionError as exc:
        assert "outside the project root" in str(exc)
    else:
        raise AssertionError("Project-local approval dir should be rejected.")


def test_hook_approval_dir_allows_external(tmp_path: Path, monkeypatch) -> None:
    approval_dir = tmp_path.parent / f"approvals-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(approval_dir))
    store = HookApprovalStore(tmp_path, SafeCodeConfig())
    store.approve("after_apply", "git status")

    assert any(approval_dir.glob("*.jsonl"))


def test_hook_approval_requires_allow_medium_switch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = False
    HookApprovalStore(tmp_path, config).approve("after_apply", "git status")

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_hook_approval_parsing_skips_malformed_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    store = HookApprovalStore(tmp_path, SafeCodeConfig())
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{broken json\n", encoding="utf-8")

    assert store.is_approved("after_apply", "git status") is False


def test_hook_approval_parsing_skips_missing_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    store = HookApprovalStore(tmp_path, SafeCodeConfig())
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('{"hook_name":"after_apply"}\n', encoding="utf-8")

    assert store.is_approved("after_apply", "git status") is False


def test_hook_approval_parsing_invalid_expires_at(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    store = HookApprovalStore(tmp_path, SafeCodeConfig())
    payload = {
        "hook_name": "after_apply",
        "command": "git status",
        "command_hash": store.command_hash("after_apply", "git status"),
        "approved_at": "2026-01-01T00:00:00Z",
        "expires_at": "not-a-date",
        "user": store._current_user(),
        "config_hash": store.config_hash(),
        "policy_version": store._policy_version(),
    }
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert store.is_approved("after_apply", "git status") is False


def test_hook_approval_user_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    store = HookApprovalStore(tmp_path, SafeCodeConfig())
    payload = {
        "hook_name": "after_apply",
        "command": "git status",
        "command_hash": store.command_hash("after_apply", "git status"),
        "approved_at": "2026-01-01T00:00:00Z",
        "expires_at": future_timestamp(),
        "user": "someone-else",
        "config_hash": store.config_hash(),
        "policy_version": store._policy_version(),
    }
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert store.is_approved("after_apply", "git status") is False


def test_hook_approval_config_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    store = HookApprovalStore(tmp_path, SafeCodeConfig())
    payload = {
        "hook_name": "after_apply",
        "command": "git status",
        "command_hash": store.command_hash("after_apply", "git status"),
        "approved_at": "2026-01-01T00:00:00Z",
        "expires_at": future_timestamp(),
        "user": store._current_user(),
        "config_hash": "tampered",
        "policy_version": store._policy_version(),
    }
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert store.is_approved("after_apply", "git status") is False


def test_hook_approval_policy_version_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    config = SafeCodeConfig()
    config.hooks.allow_medium_after_apply = True
    monkeypatch.setattr(approvals, "APPROVAL_POLICY_VERSION", "v1")
    HookApprovalStore(tmp_path, config).approve("after_apply", "git status")

    monkeypatch.setattr(approvals, "APPROVAL_POLICY_VERSION", "v2")

    assert HookApprovalStore(tmp_path, config).is_approved("after_apply", "git status") is False


def test_hook_approval_is_bound_to_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(external_approval_dir(tmp_path)))
    approved_config = SafeCodeConfig()
    approved_config.hooks.after_apply = ["git status"]
    approved_config.hooks.allow_medium_after_apply = True
    HookApprovalStore(tmp_path, approved_config).approve("after_apply", "git status")
    changed_config = SafeCodeConfig()
    changed_config.hooks.after_apply = ["git status", "echo changed"]
    changed_config.hooks.allow_medium_after_apply = True

    summary = HookRunner(tmp_path, changed_config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_audit_log_hash_chain_detects_tampering(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    logger = AuditLogger(tmp_path)
    logger.write(AuditEvent(type="one", timestamp="2026-01-01T00:00:00Z", message="first"))
    logger.write(AuditEvent(type="two", timestamp="2026-01-01T00:00:01Z", message="second"))

    ok, _ = logger.verify_integrity()
    assert ok is True

    log_file = tmp_path / ".sac" / "logs" / "events.jsonl"
    text = log_file.read_text(encoding="utf-8").replace("second", "tampered")
    log_file.write_text(text, encoding="utf-8")

    ok, message = logger.verify_integrity()
    assert ok is False
    assert "mismatch" in message


def test_audit_anchor_rejects_project_local_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))

    try:
        AuditLogger(tmp_path)
    except PermissionError as exc:
        assert "outside the project root" in str(exc)
    else:
        raise AssertionError("Project-local anchor dir should be rejected.")


def test_audit_anchor_allows_external_dir(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    logger = AuditLogger(tmp_path)
    logger.write(AuditEvent(type="one", timestamp="2026-01-01T00:00:00Z", message="first"))

    assert any(anchor_dir.glob("*.jsonl"))


def test_audit_verify_fails_when_anchor_missing(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    logger = AuditLogger(tmp_path)
    logger.write(AuditEvent(type="one", timestamp="2026-01-01T00:00:00Z", message="first"))
    for path in anchor_dir.glob("*.jsonl"):
        path.unlink()

    ok, message = logger.verify_integrity()

    assert ok is False
    assert "anchor missing" in message


def test_audit_anchor_permissions_are_restricted(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    AuditLogger(tmp_path).write(AuditEvent(type="one", timestamp="2026-01-01T00:00:00Z", message="first"))
    anchor_file = next(anchor_dir.glob("*.jsonl"))

    assert anchor_file.stat().st_mode & 0o777 == 0o600
    assert anchor_dir.stat().st_mode & 0o777 == 0o700


def test_audit_anchor_detects_full_log_rewrite(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    logger = AuditLogger(tmp_path)
    logger.write(AuditEvent(type="one", timestamp="2026-01-01T00:00:00Z", message="first"))
    logger.write(AuditEvent(type="two", timestamp="2026-01-01T00:00:01Z", message="second"))

    rewritten_events = [
        AuditEvent(type="one", timestamp="2026-01-01T00:00:00Z", message="rewritten first"),
        AuditEvent(type="two", timestamp="2026-01-01T00:00:01Z", message="rewritten second"),
    ]
    previous_hash = None
    lines = []
    for event in rewritten_events:
        event.previous_hash = previous_hash
        event.event_hash = logger._hash_event(event)
        previous_hash = event.event_hash
        lines.append(event.model_dump_json())
    (tmp_path / ".sac" / "logs" / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, message = logger.verify_integrity()

    assert ok is False
    assert "anchor mismatch" in message


def test_audit_verify_reports_legacy_events_cleanly(tmp_path: Path) -> None:
    log_file = tmp_path / ".sac" / "logs" / "events.jsonl"
    log_file.parent.mkdir(parents=True)
    log_file.write_text('{"type":"old","timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")

    ok, message = AuditLogger(tmp_path).verify_integrity()

    assert ok is False
    assert "Legacy audit event" in message


def test_checkpoint_create_rejects_path_escape(tmp_path: Path) -> None:
    proposal = PatchProposal(
        id="checkpoint-escape",
        task="escape",
        blocks=[PatchBlock(operation="update", file_path=Path("../outside.txt"), search="a", replace="b")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    try:
        CheckpointManager(tmp_path).create(proposal)
    except PermissionError as exc:
        assert "escapes project root" in str(exc)
    else:
        raise AssertionError("Checkpoint path escape should be rejected.")


def test_rollback_without_checkpoint_has_clear_error(tmp_path: Path) -> None:
    try:
        CheckpointManager(tmp_path).rollback_last()
    except FileNotFoundError as exc:
        assert "No checkpoints found" in str(exc)
    else:
        raise AssertionError("Rollback without checkpoint should fail clearly.")


def test_context_collector_skips_secret_like_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("public", encoding="utf-8")
    (tmp_path / ".env.local").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / "api_token.txt").write_text("token", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert "README.md" in context["files"]
    assert ".env.local" not in context["files"]
    assert "api_token.txt" not in context["files"]


def test_context_collector_skips_sensitive_path_segments(tmp_path: Path) -> None:
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "visible.txt").write_text("hidden", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "visible.txt").write_text("public", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert "secrets/visible.txt" not in context["files"]
    assert "src/visible.txt" in context["files"]


def test_context_collector_redacts_project_root(tmp_path: Path) -> None:
    context = ContextCollector(tmp_path).collect()

    assert context["project_root"] == "[PROJECT_ROOT]"
    assert str(tmp_path) not in str(context)


def test_context_collector_skips_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("SECRET=value", encoding="utf-8")
    (tmp_path / "linked.txt").symlink_to(outside)

    context = ContextCollector(tmp_path).collect()

    assert "linked.txt" not in context["files"]


def test_context_collector_skips_symlinked_directories(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secrets"
    outside.mkdir(exist_ok=True)
    (outside / "visible.txt").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / "linked-dir").symlink_to(outside, target_is_directory=True)

    context = ContextCollector(tmp_path).collect()

    assert "linked-dir/visible.txt" not in context["files"]


def test_context_collector_redacts_secret_content(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("API_KEY=abc123\nnormal text", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert "abc123" not in context["readme"]
    assert "[REDACTED]" in context["readme"]


def test_context_collector_redacts_json_bearer_and_aws_keys(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        '"token": "abc123",\nAuthorization: Bearer secret-token\nAKIAABCDEFGHIJKLMNOP\n',
        encoding="utf-8",
    )

    context = ContextCollector(tmp_path).collect()

    assert "abc123" not in context["readme"]
    assert "secret-token" not in context["readme"]
    assert "AKIAABCDEFGHIJKLMNOP" not in context["readme"]


def test_context_collector_redacts_github_token(tmp_path: Path) -> None:
    token = "ghp_1234567890abcdef1234567890abcdef1234"
    (tmp_path / "README.md").write_text(f"token={token}\n", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert token not in context["readme"]
    assert "[REDACTED]" in context["readme"]


def test_context_collector_redacts_jwt_token(tmp_path: Path) -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    (tmp_path / "README.md").write_text(f"{jwt}\n", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert jwt not in context["readme"]
    assert "[REDACTED]" in context["readme"]


def test_context_collector_redacts_bearer_token(tmp_path: Path) -> None:
    token = "Bearer abcdef1234567890abcdef1234567890"
    (tmp_path / "README.md").write_text(f"Authorization: {token}\n", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert "abcdef1234567890abcdef1234567890" not in context["readme"]
    assert "[REDACTED]" in context["readme"]


def test_context_collector_redacts_base64_secret(tmp_path: Path) -> None:
    secret = "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo0MTIzNDU2Nzg5MA=="
    (tmp_path / "README.md").write_text(f"{secret}\n", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert secret not in context["readme"]
    assert "[REDACTED]" in context["readme"]


def test_context_collector_caps_file_list_by_total_budget(tmp_path: Path) -> None:
    config = SafeCodeConfig(max_context_chars=30)
    (tmp_path / "README.md").write_text("public", encoding="utf-8")
    for index in range(20):
        (tmp_path / f"file-{index}.txt").write_text("x", encoding="utf-8")

    context = ContextCollector(tmp_path, config).collect()

    assert len("\n".join(context["files"])) <= config.max_context_chars


def test_context_collector_caps_large_files(tmp_path: Path) -> None:
    config = SafeCodeConfig(max_file_bytes=10)
    (tmp_path / "README.md").write_text("x" * 100, encoding="utf-8")

    context = ContextCollector(tmp_path, config).collect()

    assert context["readme"] is None


def test_patch_apply_rolls_back_on_atomic_write_failure(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("before one", encoding="utf-8")
    second.write_text("before two", encoding="utf-8")
    proposal = PatchProposal(
        id="patch-transaction",
        task="transaction",
        blocks=[
            PatchBlock(operation="update", file_path=Path("one.txt"), search="before", replace="after"),
            PatchBlock(operation="update", file_path=Path("two.txt"), search="before", replace="after"),
        ],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )
    applier = PatchApplier(tmp_path)
    original_atomic_write = applier._atomic_write
    calls = {"count": 0}

    def flaky_atomic_write(target_path: Path, content: str, file_mode: int | None = None) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("disk exploded")
        original_atomic_write(target_path, content, file_mode)

    monkeypatch.setattr(applier, "_atomic_write", flaky_atomic_write)

    try:
        applier.apply(proposal)
    except PatchValidationError as exc:
        assert "rolled back" in str(exc)
    else:
        raise AssertionError("Apply should fail and rollback.")

    assert first.read_text(encoding="utf-8") == "before one"
    assert second.read_text(encoding="utf-8") == "before two"


def test_patch_apply_preserves_file_mode(tmp_path: Path) -> None:
    target = tmp_path / "script.sh"
    target.write_text("echo before\n", encoding="utf-8")
    target.chmod(0o755)
    proposal = PatchProposal(
        id="patch-mode",
        task="mode",
        blocks=[PatchBlock(operation="update", file_path=Path("script.sh"), search="before", replace="after")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    PatchApplier(tmp_path).apply(proposal)

    assert target.read_text(encoding="utf-8") == "echo after\n"
    assert target.stat().st_mode & 0o777 == 0o755


def test_patch_apply_rejects_non_utf8_file(tmp_path: Path) -> None:
    target = tmp_path / "binary.bin"
    target.write_bytes(b"\xff\xfe")
    proposal = PatchProposal(
        id="patch-binary",
        task="binary",
        blocks=[PatchBlock(operation="update", file_path=Path("binary.bin"), search="a", replace="b")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    try:
        PatchApplier(tmp_path).apply(proposal)
    except PatchValidationError as exc:
        assert "non-UTF-8" in str(exc)
    else:
        raise AssertionError("Non-UTF-8 files should be rejected.")


def test_patch_apply_rechecks_preimage_before_write(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "README.md"
    target.write_text("before", encoding="utf-8")
    proposal = PatchProposal(
        id="patch-preimage",
        task="preimage",
        blocks=[PatchBlock(operation="update", file_path=Path("README.md"), search="before", replace="after")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )
    applier = PatchApplier(tmp_path)
    original_prepare = applier._prepare_operations

    def changing_prepare(proposal: PatchProposal):
        operations = original_prepare(proposal)
        target.write_text("changed elsewhere", encoding="utf-8")
        return operations

    monkeypatch.setattr(applier, "_prepare_operations", changing_prepare)

    try:
        applier.apply(proposal)
    except PatchValidationError as exc:
        assert "File changed after validation" in str(exc)
    else:
        raise AssertionError("Apply should reject stale preimage.")

    assert target.read_text(encoding="utf-8") == "changed elsewhere"


def test_patch_apply_rejects_symlink_swap(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "README.md"
    target.write_text("before", encoding="utf-8")
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("outside", encoding="utf-8")
    proposal = PatchProposal(
        id="patch-symlink",
        task="symlink",
        blocks=[PatchBlock(operation="update", file_path=Path("README.md"), search="before", replace="after")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )
    applier = PatchApplier(tmp_path)
    original_prepare = applier._prepare_operations

    def swapping_prepare(proposal: PatchProposal):
        operations = original_prepare(proposal)
        target.unlink()
        target.symlink_to(outside)
        return operations

    monkeypatch.setattr(applier, "_prepare_operations", swapping_prepare)

    try:
        applier.apply(proposal)
    except PatchValidationError as exc:
        assert "symlink" in str(exc)
    else:
        raise AssertionError("Apply should reject symlink swaps.")

    assert outside.read_text(encoding="utf-8") == "outside"


def test_patch_apply_still_applies_after_identity_check(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("before", encoding="utf-8")
    proposal = PatchProposal(
        id="patch-identity",
        task="identity",
        blocks=[PatchBlock(operation="update", file_path=Path("README.md"), search="before", replace="after")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    PatchApplier(tmp_path).apply(proposal)

    assert target.read_text(encoding="utf-8") == "after"


def test_orchestrator_writes_trace_id_to_audit(tmp_path: Path) -> None:
    AgentOrchestrator(tmp_path).ask("what is this")

    event = AgentOrchestrator(tmp_path).history(limit=1)[0]

    assert event.trace_id
    assert (tmp_path / ".sac" / "logs" / "traces.jsonl").exists()


def test_runtime_logger_records_exception_details(tmp_path: Path) -> None:
    logger = RuntimeLogger(tmp_path)

    try:
        raise ValueError("bad runtime")
    except ValueError as exc:
        logger.error("test", "runtime failed", exc=exc, command="demo")

    event = logger.read_recent(limit=1)[0]

    assert event.level == "error"
    assert event.error_type == "ValueError"
    assert "bad runtime" in (event.traceback or "")
    assert event.details["command"] == "demo"


def test_shell_runner_reports_missing_executable(tmp_path: Path) -> None:
    result = ShellRunner(tmp_path).run("definitely-not-a-safecode-command", approved=True)

    assert result.executed is False
    assert result.exit_code == 126


def test_command_policy_blocks_dangerous_git_args() -> None:
    decision = CommandPolicy(SafeCodeConfig()).evaluate("git reset --hard HEAD", approved=True)

    assert decision.allowed is False
    assert "destructive" in decision.reason


def test_command_policy_blocks_git_alias_shell_escape() -> None:
    decision = CommandPolicy(SafeCodeConfig()).evaluate("git -c alias.pwn=!sh status", approved=True)

    assert decision.allowed is False
    assert "arbitrary shell" in decision.reason


def test_command_policy_blocks_git_path_overrides() -> None:
    for command in [
        "git -C /tmp status",
        "git -C/tmp status",
        "git --work-tree=/tmp status",
        "git --git-dir=/tmp/.git status",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False
        assert "outside the project boundary" in decision.reason


def test_command_policy_blocks_stateful_git_commands() -> None:
    for command in [
        "git clean",
        "git clean -d",
        "git -c clean.requireForce=0 clean -d",
        "git clean -fdx",
        "git commit -m test",
        "git merge main",
        "git rebase main",
        "git pull",
        "git fetch",
        "git clone https://example.com/repo.git",
        "git checkout -- README.md",
        "git checkout README.md",
        "git restore -- README.md",
        "git restore README.md",
        "git switch main",
        "git push origin main",
        "git remote add origin https://example.com/repo.git",
        "git submodule add https://example.com/repo.git",
        "git config alias.pwn !sh",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False


def test_command_policy_blocks_git_config_execution_hooks() -> None:
    for command in [
        "git -c credential.helper=!sh status",
        "git -c core.pager=!sh status",
        "git -c core.editor=sh status",
        "git -c core.fsmonitor=sh status",
        "git -c core.askpass=sh status",
        "git -c core.hooksPath=/tmp/hooks status",
        "git -c core.sshCommand=ssh status",
        "git -c pager.log=!sh log",
        "git -c sequence.editor=sh rebase",
        "git -c diff.safe.command=sh diff",
        "git config credential.helper !sh",
        "git config core.pager !sh",
        "git config core.hooksPath /tmp/hooks",
        "git config core.sshCommand ssh",
        "git config diff.safe.command sh",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False


def test_command_policy_blocks_git_config_include_paths() -> None:
    for command in [
        "git -c include.path=/tmp/pwn status",
        "git config include.path /tmp/pwn",
        "git -c includeIf.onbranch:main.path=/tmp/pwn status",
        "git config includeIf.onbranch:main.path /tmp/pwn",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False


def test_command_policy_blocks_python_inline_code() -> None:
    decision = CommandPolicy(SafeCodeConfig()).evaluate("python -c 'print(1)'", approved=True)

    assert decision.allowed is False
    assert "arbitrary code" in decision.reason


def test_command_policy_blocks_interpreter_execution_modes() -> None:
    for command in [
        "python -m http.server",
        "python -",
        "node -e 'console.log(1)'",
        "node --eval 'console.log(1)'",
        "npm run build",
        "npx cowsay hi",
        "pip3 install demo",
        "pipx install demo",
        "uv run pytest",
        "uv tool install ruff",
        "uv pip install demo",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False


def test_command_policy_blocks_non_allowlisted_command() -> None:
    decision = CommandPolicy(SafeCodeConfig()).evaluate("curl https://example.com", approved=True)

    assert decision.allowed is False
    assert "not allowlisted" in decision.reason


# --- v1.6.1 MCP write proposal tests ---


def test_mcp_write_tool_creates_pending_proposal(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    proposal = runner.propose_write("mock", "mock.write", {"key": "value"})

    assert proposal.server == "mock"
    assert proposal.tool == "mock.write"
    assert proposal.classification == "write"
    assert proposal.status == "pending"
    assert (tmp_path / ".sac" / "pending_mcp_call.json").exists()


def test_mcp_write_proposal_requires_configured_server(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    config = SafeCodeConfig()
    config.sandbox.network_enabled = True

    try:
        MCPReadOnlyRunner(tmp_path, config).propose_write("missing", "mock.write", {})
    except PermissionError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Write proposals should require a configured MCP server.")


def test_mcp_write_proposal_rejects_disabled_server(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".sac" / "mcp.toml").write_text(
        '[servers.mock]\ncommand = "echo ok"\nenabled = false\n',
        encoding="utf-8",
    )
    config = SafeCodeConfig()
    config.sandbox.network_enabled = True

    try:
        MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {})
    except PermissionError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Write proposals should reject disabled MCP servers.")


def test_mcp_write_proposal_rejects_disallowed_server_command(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    write_mcp_config(tmp_path, "curl https://example.com")
    config = SafeCodeConfig()
    config.sandbox.network_enabled = True

    try:
        MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {})
    except PermissionError as exc:
        assert "not allowlisted" in str(exc)
    else:
        raise AssertionError("Write proposals should reject disallowed MCP server commands.")


def test_mcp_write_proposal_includes_required_fields(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    proposal = runner.propose_write("mock", "mock.create", {"name": "test"})

    assert proposal.proposal_id
    assert proposal.server == "mock"
    assert proposal.tool == "mock.create"
    assert proposal.input_hash
    assert len(proposal.input_hash) == 64
    assert proposal.status == "pending"
    assert proposal.risk_level == "high"
    assert proposal.reason
    assert proposal.created_at


def test_mcp_write_proposal_does_not_execute_server(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    run_called = []

    def fake_run(*args, **kwargs):
        run_called.append(True)
        return subprocess.CompletedProcess([], 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = MCPReadOnlyRunner(tmp_path, config)
    runner.propose_write("mock", "mock.write", {"key": "value"})

    assert len(run_called) == 0


def test_mcp_write_proposal_redacts_secrets_in_input(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    proposal = runner.propose_write("mock", "mock.write", {"api_key": "sk-abc123secret"})

    raw_json = (tmp_path / ".sac" / "pending_mcp_call.json").read_text(encoding="utf-8")
    assert "sk-abc123secret" not in raw_json
    assert "[REDACTED]" in raw_json


def test_mcp_second_write_proposal_blocked_when_pending(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    runner.propose_write("mock", "mock.write", {"first": True})

    try:
        runner.propose_write("mock", "mock.create", {"second": True})
    except FileExistsError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Second proposal should be blocked when one is pending.")


def test_mcp_corrupt_pending_blocks_new_proposal(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)
    pending_path = tmp_path / ".sac" / "pending_mcp_call.json"
    pending_path.write_text("{broken json", encoding="utf-8")
    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    try:
        MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {"key": "value"})
    except FileExistsError as exc:
        assert "cannot be parsed" in str(exc)
    else:
        raise AssertionError("Corrupt pending proposal should block new proposals.")


def test_mcp_write_proposal_rejects_oversized_input(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)
    config = SafeCodeConfig(max_context_chars=30)
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    try:
        MCPReadOnlyRunner(tmp_path, config).propose_write("mock", "mock.write", {"payload": "x" * 200})
    except PermissionError as exc:
        assert "size limits" in str(exc)
    else:
        raise AssertionError("Oversized MCP write proposal input should be rejected.")


def test_mcp_discard_removes_pending_proposal(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    runner.propose_write("mock", "mock.write", {"key": "value"})

    pending_path = tmp_path / ".sac" / "pending_mcp_call.json"
    assert pending_path.exists()

    store = MCPWriteProposalStore(tmp_path, config)
    removed = store.discard_pending()

    assert removed is True
    assert not pending_path.exists()


def test_mcp_discard_writes_audit_event(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    runner.propose_write("mock", "mock.write", {"key": "value"})

    from safecode.cli import mcp_discard

    monkeypatch.chdir(tmp_path)
    mcp_discard()

    events = AuditLogger(tmp_path, config).read_recent(limit=10)
    event_types = [event.type for event in events]
    assert "mcp_write_discarded" in event_types
    discard_event = next(event for event in events if event.type == "mcp_write_discarded")
    assert discard_event.metadata["server"] == "mock"
    assert discard_event.metadata["tool"] == "mock.write"


def test_mcp_unknown_tool_is_blocked_for_write_proposal(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)

    try:
        runner.propose_write("mock", "mock.xyzzy", {})
    except PermissionError as exc:
        assert "unknown classification" in str(exc).lower()
    else:
        raise AssertionError("Unknown tool should be blocked for write proposal.")


def test_mcp_readonly_tool_rejected_by_propose_write(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)

    try:
        runner.propose_write("mock", "mock.list", {"query": "test"})
    except ValueError as exc:
        assert "read-only" in str(exc).lower()
    else:
        raise AssertionError("Read-only tool should be rejected by propose_write.")


def test_mcp_propose_write_writes_audit_event(tmp_path: Path, monkeypatch) -> None:
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    runner.propose_write("mock", "mock.write", {"key": "value"})

    events = AuditLogger(tmp_path, config).read_recent(limit=10)
    event_types = [event.type for event in events]
    assert "mcp_write_proposed" in event_types


def test_mcp_discard_when_none_pending_is_safe(tmp_path: Path) -> None:
    store = MCPWriteProposalStore(tmp_path)
    removed = store.discard_pending()

    assert removed is False


def test_mcp_load_pending_returns_none_when_no_file(tmp_path: Path) -> None:
    store = MCPWriteProposalStore(tmp_path)
    proposal = store.load_pending()

    assert proposal is None


def test_mcp_existing_readonly_tests_still_work(tmp_path: Path, monkeypatch) -> None:
    """Verify v1.6.0 read-only MCP behavior still works after v1.6.1 changes."""
    anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    server_path = write_mock_mcp_server(tmp_path)
    command = shlex.join([sys.executable, str(server_path)])
    write_mcp_config(tmp_path, command)

    config = SafeCodeConfig()
    config.shell.allowed_commands = [sys.executable]
    config.shell.require_confirm_for_medium = False
    config.sandbox.network_enabled = True

    runner = MCPReadOnlyRunner(tmp_path, config)
    result = runner.call_readonly("mock", "mock.list", {"query": "hello"})

    assert result.blocked is False
    assert result.exit_code == 0
    assert "ok" in result.output

    events = AuditLogger(tmp_path, config).read_recent(limit=10)
    event_types = [event.type for event in events]
    assert "mcp_call_proposed" in event_types
    assert "mcp_call_completed" in event_types
