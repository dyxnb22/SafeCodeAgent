"""Run configured project hooks through the controlled shell runner."""

from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.hooks.approvals import HookApprovalStore
from safecode.shell.runner import ShellRunResult, ShellRunner
from safecode.utils.time import utc_now_iso


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
        runner = ShellRunner(self.project_root, self.config)
        results: list[ShellRunResult] = []
        for command in self.config.hooks.after_apply:
            self._audit("hook_proposed", command, "pending", "after_apply hook proposed")
            approved = self.config.hooks.allow_medium_after_apply and self.approvals.is_approved("after_apply", command)
            if approved:
                self._audit("hook_approval_used", command, "success", "stored hook approval matched")
            elif not self.config.hooks.allow_medium_after_apply:
                self._audit("hook_approval_required", command, "blocked", "hook execution disabled by config")
            result = runner.run(command, approved=approved)
            results.append(result)
            if not result.executed and result.exit_code == 125:
                self._audit("hook_approval_required", command, "blocked", result.stderr)
            else:
                self._audit(
                    "hook_completed",
                    command,
                    "success" if result.exit_code == 0 else "failed",
                    result.stderr or result.stdout or "after_apply hook finished",
                    result.exit_code,
                )
        return HookRunSummary("after_apply", results)

    def _audit(
        self,
        event_type: str,
        command: str,
        status: str,
        message: str,
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
                metadata={"hook": "after_apply"},
            )
        )
