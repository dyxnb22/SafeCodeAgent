"""Run shell commands through SafeCode policy checks."""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.policy.commands import CommandDecision, CommandPolicy
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.sandbox.network import NetworkPolicy
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


@dataclass(frozen=True)
class ShellCommandProposal:
    """Policy-gated proposal for a command before execution."""

    command: str
    decision: CommandDecision

    @property
    def status(self) -> str:
        if self.decision.allowed:
            return "allowed"
        if self.decision.requires_approval:
            return "approval_required"
        return "blocked"


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

    def propose(self, command: str, approved: bool = False) -> ShellCommandProposal:
        """Evaluate a command through policy without executing it."""
        return ShellCommandProposal(command=command, decision=self.policy.evaluate(command, approved=approved))

    def run(self, command: str, approved: bool = False) -> ShellRunResult:
        """Run a command when policy allows it."""
        decision = self.policy.evaluate(command, approved=approved)
        risk = decision.risk
        if not decision.allowed:
            exit_code = 125 if decision.requires_approval else 126
            return ShellRunResult(command, risk, exit_code, "", decision.reason, 0, False)

        network_block = self._network_block_reason(risk.tokens)
        if network_block:
            return ShellRunResult(command, risk, 126, "", network_block, 0, False)

        started = time.perf_counter()
        env = self._sanitized_env()
        try:
            completed = subprocess.run(
                risk.tokens,
                cwd=self.project_root,
                text=True,
                capture_output=True,
                env=env,
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

    def _sanitized_env(self) -> dict[str, str]:
        """Return environment variables with Git override injection removed."""
        env = dict(os.environ)
        blocked_keys = {
            "GIT_ASKPASS",
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_EDITOR",
            "GIT_PAGER",
            "GIT_SEQUENCE_EDITOR",
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "LESS",
            "PAGER",
            "SSH_ASKPASS",
        }
        for key in blocked_keys:
            env.pop(key, None)
        for key in list(env.keys()):
            if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
                env.pop(key, None)
        return env

    def _network_block_reason(self, tokens: list[str]) -> str | None:
        """Return a policy error when network access is not permitted."""
        if not tokens:
            return None
        command = tokens[0].lower()
        policy = NetworkPolicy(self.config)
        if command == "git":
            subcommand, index = self._git_subcommand(tokens)
            if not subcommand:
                return None
            lowered_subcommand = subcommand.lower()
            if lowered_subcommand in {"fetch", "pull", "push", "clone", "remote", "submodule"}:
                target = self._extract_network_target(tokens[index + 1 :])
                return self._check_network_policy(policy, target, f"git {lowered_subcommand}")
            return None
        if command in {"curl", "wget", "ssh", "scp", "rsync"}:
            target = self._extract_network_target(tokens[1:])
            return self._check_network_policy(policy, target, command)
        if command in {"npm", "pnpm"} and any(
            token in {"install", "add", "update", "ci", "audit", "publish"} for token in [arg.lower() for arg in tokens[1:]]
        ):
            return self._check_network_policy(policy, None, command)
        if command == "npx":
            return self._check_network_policy(policy, None, command)
        if command in {"pip", "pip3", "pipx"} and "install" in [token.lower() for token in tokens[1:]]:
            return self._check_network_policy(policy, None, command)
        if command == "uv":
            lowered_args = [token.lower() for token in tokens[1:]]
            if any(token in {"pip", "tool", "run"} for token in lowered_args):
                return self._check_network_policy(policy, None, command)
        return None

    def _check_network_policy(self, policy: NetworkPolicy, target: str | None, label: str) -> str | None:
        if not self.config.sandbox.network_enabled:
            return "Network access is disabled by policy."
        if self.config.sandbox.network_allowlist:
            if not target:
                return f"Network access requires an allowlisted host for {label}."
            try:
                policy.assert_allowed(target)
            except PermissionError as exc:
                return str(exc)
        return None

    def _extract_network_target(self, args: list[str]) -> str | None:
        for token in args:
            if token.startswith("-"):
                continue
            return self._normalize_network_target(token)
        return None

    def _normalize_network_target(self, token: str) -> str | None:
        if token.startswith(("/", "./", "../")):
            return None
        if "://" in token:
            return token
        if "@" in token and ":" in token:
            user_host, path = token.split(":", 1)
            return f"ssh://{user_host}/{path}"
        return f"ssh://{token}" if token else None

    def _git_subcommand(self, tokens: list[str]) -> tuple[str | None, int]:
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token in {"-c", "-C"}:
                index += 2
                continue
            if token in {"--work-tree", "--git-dir"}:
                index += 2
                continue
            if token.startswith("-c") or token.startswith("-C"):
                index += 1
                continue
            if token.startswith("--work-tree") or token.startswith("--git-dir"):
                index += 1
                continue
            if token.startswith("-"):
                index += 1
                continue
            return token, index
        return None, -1
