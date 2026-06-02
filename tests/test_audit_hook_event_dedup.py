"""Tests for v2.8.9 audit-and-hook-event-dedup.

Verifies:
- When hooks are disabled by policy (allow_medium_after_apply=False), only
  hook_skipped_by_policy is emitted — NOT hook_approval_required.
- When hooks are allowed but approval is missing, hook_approval_required is
  emitted and hook_skipped_by_policy is not.
- hook_skipped_by_policy is a distinct event type separate from hook_approval_required.
- Audit chain verification remains backward-compatible (old logs still verify).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.hooks.runner import HookRunner
from safecode.shell.runner import ShellRunResult
from safecode.shell.risk import ShellRisk, RiskLevel


def _config_hooks_disabled() -> SafeCodeConfig:
    """Config with hooks.allow_medium_after_apply=False and one after_apply command."""
    config = SafeCodeConfig()
    config.hooks.after_apply = ["echo after-apply"]
    config.hooks.allow_medium_after_apply = False
    return config


def _config_hooks_allowed_no_approval() -> SafeCodeConfig:
    """Config with hooks.allow_medium_after_apply=True but no stored approval."""
    config = SafeCodeConfig()
    config.hooks.after_apply = ["echo after-apply"]
    config.hooks.allow_medium_after_apply = True
    return config


def _collect_audit_events(
    project_root: Path,
    config: SafeCodeConfig,
    *,
    run_result: ShellRunResult | None = None,
) -> list[str]:
    """Run after_apply hooks and return the list of emitted event types.

    Pass run_result to override what the shell runner returns (for unit-testing
    specific runner outcomes without needing an actual shell command).
    """
    written: list[str] = []

    def fake_write(event: AuditEvent) -> None:
        written.append(event.type)

    hook_runner = HookRunner(project_root, config=config)
    hook_runner.audit_logger.write = fake_write  # type: ignore[method-assign]

    if run_result is not None:
        with patch("safecode.hooks.runner.ShellRunner.run", return_value=run_result):
            hook_runner.run_after_apply()
    else:
        hook_runner.run_after_apply()

    return written


def _approval_required_result() -> ShellRunResult:
    """ShellRunResult simulating an unapproved medium-risk command."""
    risk = ShellRisk(level=RiskLevel.MEDIUM, reasons=["medium risk"], tokens=["echo"])
    return ShellRunResult(
        command="echo after-apply",
        risk=risk,
        exit_code=125,
        stdout="",
        stderr="Approval required for medium-risk command.",
        duration_ms=0,
        executed=False,
    )


# ── Skipped-by-policy: no duplicate hook_approval_required ───────────────────


class TestSkippedByPolicyDedup:
    def test_no_hook_approval_required_when_disabled(self, tmp_path):
        """hook_skipped_by_policy does not produce a duplicate hook_approval_required."""
        config = _config_hooks_disabled()
        events = _collect_audit_events(tmp_path, config)
        assert "hook_approval_required" not in events, (
            f"hook_approval_required must not fire when policy disables hooks: {events}"
        )

    def test_hook_skipped_by_policy_emitted(self, tmp_path):
        """hook_skipped_by_policy is emitted when allow_medium_after_apply=False."""
        config = _config_hooks_disabled()
        events = _collect_audit_events(tmp_path, config)
        assert "hook_skipped_by_policy" in events, (
            f"Expected hook_skipped_by_policy in events: {events}"
        )

    def test_only_skipped_events_for_disabled_hooks(self, tmp_path):
        """When hooks are disabled, no hook_completed or hook_approval_required events."""
        config = _config_hooks_disabled()
        events = _collect_audit_events(tmp_path, config)
        assert "hook_approval_required" not in events
        assert "hook_completed" not in events

    def test_hook_proposed_still_emitted_when_disabled(self, tmp_path):
        """hook_proposed is still emitted even when hooks are disabled."""
        config = _config_hooks_disabled()
        events = _collect_audit_events(tmp_path, config)
        assert "hook_proposed" in events


# ── Approval-required: emitted when policy allows but approval missing ────────


class TestApprovalRequiredEvent:
    def test_hook_approval_required_when_allowed_but_unapproved(self, tmp_path):
        """When policy allows hooks but the runner returns 125, hook_approval_required fires."""
        config = _config_hooks_allowed_no_approval()
        events = _collect_audit_events(tmp_path, config, run_result=_approval_required_result())
        assert "hook_approval_required" in events, (
            f"Expected hook_approval_required when policy allows but no approval: {events}"
        )

    def test_no_hook_skipped_by_policy_when_approval_missing(self, tmp_path):
        """hook_skipped_by_policy must not fire when policy allows hooks."""
        config = _config_hooks_allowed_no_approval()
        events = _collect_audit_events(tmp_path, config, run_result=_approval_required_result())
        assert "hook_skipped_by_policy" not in events, (
            f"hook_skipped_by_policy must not fire when allow_medium=True: {events}"
        )

    def test_no_hook_completed_when_approval_required(self, tmp_path):
        """hook_completed must not fire alongside hook_approval_required."""
        config = _config_hooks_allowed_no_approval()
        events = _collect_audit_events(tmp_path, config, run_result=_approval_required_result())
        assert "hook_completed" not in events, (
            f"hook_completed must not fire when hook_approval_required fires: {events}"
        )


# ── Distinct event types ──────────────────────────────────────────────────────


class TestDistinctEventTypes:
    def test_hook_skipped_by_policy_is_distinct_from_hook_approval_required(self):
        """The two event types are distinct strings."""
        assert "hook_skipped_by_policy" != "hook_approval_required"

    def test_hook_skipped_by_policy_is_known_event_type(self, tmp_path):
        """AuditEvent accepts hook_skipped_by_policy as a valid type."""
        from safecode.utils.time import utc_now_iso
        event = AuditEvent(
            type="hook_skipped_by_policy",
            timestamp=utc_now_iso(),
            status="blocked",
            command="echo test",
            message="hook execution disabled by config",
            metadata={"hook": "after_apply"},
        )
        assert event.type == "hook_skipped_by_policy"

    def test_hook_skipped_by_policy_serializes(self, tmp_path):
        """hook_skipped_by_policy event serializes to JSON without error."""
        import json
        from safecode.utils.time import utc_now_iso
        event = AuditEvent(
            type="hook_skipped_by_policy",
            timestamp=utc_now_iso(),
            status="blocked",
            command="echo test",
            message="hook execution disabled by config",
            metadata={"hook": "after_apply"},
        )
        serialized = json.loads(event.model_dump_json())
        assert serialized["type"] == "hook_skipped_by_policy"


# ── Backward-compatible audit chain verification ──────────────────────────────


class TestAuditChainBackwardCompatibility:
    def test_old_log_without_hook_skipped_still_verifies(self, tmp_path):
        """An audit log written before hook_skipped_by_policy existed still verifies."""
        from safecode.audit.logger import AuditLogger
        from safecode.utils.time import utc_now_iso

        logger = AuditLogger(tmp_path)
        logger.write(AuditEvent(type="hook_proposed", timestamp=utc_now_iso(), status="pending"))
        logger.write(AuditEvent(type="hook_approval_required", timestamp=utc_now_iso(), status="blocked"))
        ok, msg = logger.verify_integrity()
        assert ok, f"Old-style log without hook_skipped_by_policy should verify: {msg}"

    def test_new_log_with_skipped_by_policy_verifies(self, tmp_path):
        """A new audit log containing hook_skipped_by_policy events also verifies."""
        from safecode.audit.logger import AuditLogger
        from safecode.utils.time import utc_now_iso

        logger = AuditLogger(tmp_path)
        logger.write(AuditEvent(type="hook_proposed", timestamp=utc_now_iso(), status="pending"))
        logger.write(AuditEvent(type="hook_skipped_by_policy", timestamp=utc_now_iso(), status="blocked"))
        ok, msg = logger.verify_integrity()
        assert ok, f"Log with hook_skipped_by_policy should verify: {msg}"

    def test_mixed_log_verifies(self, tmp_path):
        """A log with both hook_skipped_by_policy and hook_approval_required verifies."""
        from safecode.audit.logger import AuditLogger
        from safecode.utils.time import utc_now_iso

        logger = AuditLogger(tmp_path)
        logger.write(AuditEvent(type="hook_proposed", timestamp=utc_now_iso(), status="pending"))
        logger.write(AuditEvent(type="hook_skipped_by_policy", timestamp=utc_now_iso(), status="blocked"))
        logger.write(AuditEvent(type="hook_proposed", timestamp=utc_now_iso(), status="pending"))
        logger.write(AuditEvent(type="hook_approval_required", timestamp=utc_now_iso(), status="blocked"))
        ok, msg = logger.verify_integrity()
        assert ok, f"Mixed log should verify: {msg}"
