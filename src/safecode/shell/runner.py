"""Run shell commands through SafeCode policy checks."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.policy.commands import CommandPolicy
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.shell.risk import ShellRisk, ShellRiskClassifier


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
        self.policy = CommandPolicy(self.config)
        FilesystemBoundary(project_root, self.config).validate(project_root)

    def assess(self, command: str) -> ShellRisk:
        """Classify a command without executing it."""
        return self.classifier.classify(command)

    def run(self, command: str, approved: bool = False) -> ShellRunResult:
        """Run a command when policy allows it."""
        decision = self.policy.evaluate(command, approved=approved)
        risk = decision.risk
        if not decision.allowed:
            exit_code = 125 if decision.requires_approval else 126
            return ShellRunResult(command, risk, exit_code, "", decision.reason, 0, False)

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                risk.tokens,
                cwd=self.project_root,
                text=True,
                capture_output=True,
                timeout=self.config.shell.default_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ShellRunResult(command, risk, 124, exc.stdout or "", exc.stderr or "Command timed out.", duration_ms, True)
        except FileNotFoundError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ShellRunResult(command, risk, 127, "", str(exc), duration_ms, False)
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
