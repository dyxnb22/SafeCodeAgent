"""Run shell commands through SafeCode policy checks."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.shell.risk import RiskLevel, ShellRisk, ShellRiskClassifier


@dataclass(frozen=True)
class ShellRunResult:
    """Result of a controlled command run."""

    command: str
    risk: ShellRisk
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    executed: bool


class ShellRunner:
    """Execute commands only after risk classification."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.classifier = ShellRiskClassifier()

    def assess(self, command: str) -> ShellRisk:
        """Classify a command without executing it."""
        return self.classifier.classify(command)

    def run(self, command: str, approved: bool = False) -> ShellRunResult:
        """Run a command when policy allows it."""
        risk = self.assess(command)
        if risk.level == RiskLevel.HIGH and self.config.shell.block_high_risk:
            return ShellRunResult(command, risk, 126, "", "Blocked high-risk command.", 0, False)
        if risk.level == RiskLevel.MEDIUM and self.config.shell.require_confirm_for_medium and not approved:
            return ShellRunResult(command, risk, 125, "", "Approval required for medium-risk command.", 0, False)
        if not risk.tokens:
            return ShellRunResult(command, risk, 125, "", "No executable tokens found.", 0, False)

        started = time.perf_counter()
        completed = subprocess.run(
            risk.tokens,
            cwd=self.project_root,
            text=True,
            capture_output=True,
            timeout=self.config.shell.default_timeout_seconds,
            check=False,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ShellRunResult(
            command=command,
            risk=risk,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
            executed=True,
        )
