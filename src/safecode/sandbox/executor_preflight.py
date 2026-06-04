"""Sandbox executor promotion preflight for v3.11.2."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapabilityDetector
from safecode.utils.time import utc_now_iso

PREFLIGHT_SCHEMA_VERSION = "v1"

_BACKEND_ALIASES = {
    "noop": SandboxBackend.NONE,
    "none": SandboxBackend.NONE,
    "docker": SandboxBackend.DOCKER,
    "seatbelt": SandboxBackend.MACOS_SEATBELT,
    "macos_seatbelt": SandboxBackend.MACOS_SEATBELT,
    "bubblewrap": SandboxBackend.LINUX_BUBBLEWRAP,
    "linux_bubblewrap": SandboxBackend.LINUX_BUBBLEWRAP,
}

_ENV_KEYS = {
    SandboxBackend.DOCKER: "SAFECODE_SANDBOX_DOCKER",
    SandboxBackend.MACOS_SEATBELT: "SAFECODE_SANDBOX_SEATBELT",
    SandboxBackend.LINUX_BUBBLEWRAP: "SAFECODE_SANDBOX_BUBBLEWRAP",
}


@dataclass(frozen=True)
class ExecutorPreflightResult:
    """Result of a backend executor promotion preflight."""

    backend: str
    passed: bool
    promotion_state: str
    env_var: str | None
    checks: dict[str, bool]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "passed": self.passed,
            "promotion_state": self.promotion_state,
            "env_var": self.env_var,
            "checks": dict(sorted(self.checks.items())),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def normalize_executor_backend(name: str) -> SandboxBackend:
    """Return canonical backend enum for CLI/input aliases."""
    try:
        return _BACKEND_ALIASES[name]
    except KeyError as exc:
        valid = ", ".join(sorted(_BACKEND_ALIASES))
        raise ValueError(f"Unknown sandbox backend {name!r}. Use one of: {valid}.") from exc


def executor_env_var(backend: str | SandboxBackend) -> str | None:
    """Return the explicit opt-in env var for a real-execution backend."""
    target = normalize_executor_backend(backend) if isinstance(backend, str) else backend
    return _ENV_KEYS.get(target)


def has_executor_preflight_pass(project_root: Path, backend: str | SandboxBackend) -> bool:
    """Return True when the current checkout has a passing preflight record."""
    target = normalize_executor_backend(backend) if isinstance(backend, str) else backend
    path = _record_path(project_root, target)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        data.get("_schema_version") == PREFLIGHT_SCHEMA_VERSION
        and data.get("backend") == target.value
        and data.get("passed") is True
    )


def real_execution_enabled(project_root: Path, backend: str | SandboxBackend) -> tuple[bool, str]:
    """Return whether real execution is enabled for backend."""
    target = normalize_executor_backend(backend) if isinstance(backend, str) else backend
    env_var = executor_env_var(target)
    if env_var is None:
        return True, "Noop backend keeps default policy-gated behavior."
    if os.getenv(env_var) != "1":
        return False, f"Set {env_var}=1 to opt in to real {target.value} execution."
    if not has_executor_preflight_pass(project_root, target):
        return False, f"Run 'sac sandbox executor-preflight {target.value}' successfully before real execution."
    return True, f"Real {target.value} execution enabled."


class SandboxExecutorPreflight:
    """Run a backend executor preflight without real user workload execution."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)

    def run(self, backend_name: str) -> ExecutorPreflightResult:
        backend = normalize_executor_backend(backend_name)
        result = self._run_backend(backend)
        self._audit(result)
        if result.passed:
            self._save(result)
        return result

    def _run_backend(self, backend: SandboxBackend) -> ExecutorPreflightResult:
        capability = self._capability_for(backend)
        checks: dict[str, bool] = {
            "capability_available": capability is not None and capability.available,
            "supports_execution": False,
            "plan_smoke": False,
            "network_disabled_by_default": False,
            "executor_smoke": False,
        }
        reasons: list[str] = []
        warnings: list[str] = []
        if backend == SandboxBackend.NONE:
            adapter = NoopSandboxAdapter()
        elif capability is not None and backend == SandboxBackend.DOCKER:
            adapter = DockerSandboxAdapter(capability, self.project_root, self.config)
        elif capability is not None and backend == SandboxBackend.MACOS_SEATBELT:
            adapter = MacOSSeatbeltAdapter(capability, self.project_root, self.config)
        elif capability is not None and backend == SandboxBackend.LINUX_BUBBLEWRAP:
            adapter = LinuxBubblewrapAdapter(capability, self.project_root, self.config)
        else:
            adapter = None

        if adapter is None:
            reasons.append(f"Backend {backend.value} is unavailable on this host.")
        else:
            checks["supports_execution"] = adapter.supports_execution()
            try:
                request = SandboxExecutionRequest(
                    command=["echo", "safecode-executor-preflight"],
                    cwd=self.project_root,
                    purpose="executor-preflight",
                    allow_network=False,
                    readonly_filesystem=True,
                    writable_paths=[],
                    env={},
                    timeout_seconds=5,
                )
                plan = adapter.build_plan(request)
                checks["plan_smoke"] = plan.backend == backend and list(plan.command) == request.command
                checks["network_disabled_by_default"] = plan.network_enabled is False
                checks["executor_smoke"] = self._executor_smoke(backend, plan)
                warnings.extend(plan.warnings)
            except Exception as exc:
                reasons.append(f"Executor smoke failed closed: {type(exc).__name__}.")

        if not checks["capability_available"]:
            reasons.append(f"Backend {backend.value} capability is not available.")
        if not checks["supports_execution"]:
            reasons.append(f"Backend {backend.value} does not support execution.")
        if not checks["plan_smoke"]:
            reasons.append(f"Backend {backend.value} plan smoke did not pass.")
        if not checks["network_disabled_by_default"]:
            reasons.append(f"Backend {backend.value} did not preserve network-disabled default.")
        if not checks["executor_smoke"]:
            reasons.append(f"Backend {backend.value} executor-only smoke did not pass.")

        passed = all(checks.values())
        state = "opt-in-real-execution" if passed and backend != SandboxBackend.NONE else "policy-gated" if passed else "preview"
        return ExecutorPreflightResult(
            backend=backend.value,
            passed=passed,
            promotion_state=state,
            env_var=executor_env_var(backend),
            checks=checks,
            reasons=sorted(set(reasons)),
            warnings=sorted(set(warnings)),
        )

    def _capability_for(self, backend: SandboxBackend):
        for cap in SandboxCapabilityDetector().detect_all():
            if cap.backend == backend:
                return cap
        return None

    def _executor_smoke(self, backend: SandboxBackend, plan) -> bool:
        if backend == SandboxBackend.NONE:
            return True
        if backend == SandboxBackend.DOCKER:
            return bool(plan.container_preview) and "--privileged" not in plan.container_preview
        if backend == SandboxBackend.MACOS_SEATBELT:
            return bool(plan.profile_preview) and "network access is DISABLED" in plan.profile_preview
        if backend == SandboxBackend.LINUX_BUBBLEWRAP:
            return bool(plan.args_preview) and "--unshare-net" in plan.args_preview
        return False

    def _save(self, result: ExecutorPreflightResult) -> None:
        path = _record_path(self.project_root, SandboxBackend(result.backend))
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"_schema_version": PREFLIGHT_SCHEMA_VERSION, **result.to_dict()}
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _audit(self, result: ExecutorPreflightResult) -> None:
        AuditLogger(self.project_root, self.config).write(
            AuditEvent(
                type="sandbox_executor_preflight_checked",
                timestamp=utc_now_iso(),
                status="success" if result.passed else "blocked",
                message="Sandbox executor preflight passed." if result.passed else "Sandbox executor preflight blocked.",
                metadata={
                    "backend": result.backend,
                    "passed": str(result.passed).lower(),
                    "promotion_state": result.promotion_state,
                    "env_var": result.env_var or "",
                },
            )
        )


def _record_path(project_root: Path, backend: SandboxBackend) -> Path:
    return project_root / ".sac" / "sandbox_executor_preflight" / f"{backend.value}.json"
