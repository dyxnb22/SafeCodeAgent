"""Run configured project hooks through the controlled shell runner."""

from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.hooks.approvals import HookApprovalStore
from safecode.shell.runner import ShellRunResult, ShellRunner
from safecode.utils.time import utc_now_iso


def is_test_command(command: str) -> bool:
    """Return true when a shell command looks like a test command."""
    lowered = command.lower()
    markers = (
        "pytest",
        "python -m pytest",
        "npm test",
        "pnpm test",
        "yarn test",
        "go test",
        "cargo test",
        "mvn test",
        "gradle test",
        "ctest",
    )
    return any(marker in lowered for marker in markers)


@dataclass(frozen=True)
class HookRunSummary:
    """Hook execution summary."""

    hook_name: str
    results: list[ShellRunResult]


class HookRunner:
    """Run hooks defined in SafeCodeConfig."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.audit_logger = AuditLogger(project_root, self.config)
        self.approvals = HookApprovalStore(project_root, self.config)

    def run_after_apply(self) -> HookRunSummary:
        """Run after_apply commands."""
        return self.run_stage("after_apply")

    def run_before_command(self) -> HookRunSummary:
        """Run before_command commands."""
        return self.run_stage("before_command")

    def run_after_edit(self) -> HookRunSummary:
        """Run after_edit commands."""
        return self.run_stage("after_edit")

    def run_after_test(self) -> HookRunSummary:
        """Run after_test commands."""
        return self.run_stage("after_test")

    def run_stage(self, hook_name: str) -> HookRunSummary:
        """Run configured commands for one hook stage."""
        if hook_name not in {"before_command", "after_edit", "after_test", "after_apply"}:
            raise ValueError(f"unknown hook stage: {hook_name}")
        commands = list(getattr(self.config.hooks, hook_name))
        runner = ShellRunner(self.project_root, self.config)
        results: list[ShellRunResult] = []
        for command in commands:
            self._audit("hook_proposed", command, "pending", f"{hook_name} hook proposed", hook_name)
            skipped_by_policy = not self.config.hooks.allow_medium_after_apply
            approved = (not skipped_by_policy) and self.approvals.is_approved(hook_name, command)
            if approved:
                self._audit("hook_approval_used", command, "success", "stored hook approval matched", hook_name)
            elif skipped_by_policy:
                self._audit("hook_skipped_by_policy", command, "blocked", "hook execution disabled by config", hook_name)
            result = runner.run(command, approved=approved)
            results.append(result)
            if skipped_by_policy:
                # hook_skipped_by_policy already emitted; no further event for this command.
                pass
            elif not result.executed and result.exit_code == 125:
                # Policy allows hooks but this specific command lacked approval.
                self._audit("hook_approval_required", command, "blocked", result.stderr, hook_name)
            else:
                self._audit(
                    "hook_completed",
                    command,
                    "success" if result.exit_code == 0 else "failed",
                    result.stderr or result.stdout or f"{hook_name} hook finished",
                    hook_name,
                    result.exit_code,
                )
        return HookRunSummary(hook_name, results)

    def _audit(
        self,
        event_type: str,
        command: str,
        status: str,
        message: str,
        hook_name: str,
        exit_code: int | None = None,
    ) -> None:
        """Write one hook audit event."""
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status=status,
                command=command,
                exit_code=exit_code,
                message=message,
                metadata={"hook": hook_name},
            )
        )
