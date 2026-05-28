from pathlib import Path

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
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.patch.applier import PatchApplier
from safecode.policy.commands import CommandPolicy
from safecode.patch.validator import PatchValidationError, PatchValidator
from safecode.shell.risk import RiskLevel, ShellRiskClassifier
from safecode.shell.runner import ShellRunner


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
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / "user-approvals"))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = True

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_approved_hook_uses_persisted_approval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / "user-approvals"))
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
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / "trusted-user-approvals"))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = True
    project_store = tmp_path / ".sac" / "approvals"
    project_store.mkdir(parents=True)
    (project_store / "hooks.jsonl").write_text('{"command":"git status"}\n', encoding="utf-8")

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_hook_approval_requires_allow_medium_switch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / "user-approvals"))
    config = SafeCodeConfig()
    config.hooks.after_apply = ["git status"]
    config.hooks.allow_medium_after_apply = False
    HookApprovalStore(tmp_path, config).approve("after_apply", "git status")

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_hook_approval_is_bound_to_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(tmp_path / "user-approvals"))
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
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
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


def test_audit_anchor_detects_full_log_rewrite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
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
        "git --work-tree=/tmp status",
        "git --git-dir=/tmp/.git status",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False
        assert "outside the project boundary" in decision.reason


def test_command_policy_blocks_stateful_git_commands() -> None:
    for command in [
        "git clean -fdx",
        "git checkout -- README.md",
        "git restore -- README.md",
        "git switch main",
        "git push origin main",
        "git config alias.pwn !sh",
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
        "node -e 'console.log(1)'",
        "npm run build",
        "uv run pytest",
        "uv tool install ruff",
    ]:
        decision = CommandPolicy(SafeCodeConfig()).evaluate(command, approved=True)

        assert decision.allowed is False


def test_command_policy_blocks_non_allowlisted_command() -> None:
    decision = CommandPolicy(SafeCodeConfig()).evaluate("curl https://example.com", approved=True)

    assert decision.allowed is False
    assert "not allowlisted" in decision.reason
