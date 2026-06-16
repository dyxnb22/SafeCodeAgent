"""Diagnostics-aware context collection for coding tasks.

This module runs local, read-only diagnostic commands with bounded output and
without shell expansion. It is deliberately lightweight: diagnostics are context
signals, not a replacement for explicit validation after edits.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.shell.runner import ShellRunner

_MAX_OUTPUT_CHARS = 4000


@dataclass(frozen=True)
class DiagnosticCommandResult:
    """One diagnostic command result."""

    name: str
    command: list[str]
    exit_code: int
    output: str
    duration_ms: int
    executed: bool
    reason: str = ""

    def as_context(self) -> dict:
        return {
            "name": self.name,
            "command": " ".join(self.command),
            "exit_code": self.exit_code,
            "executed": self.executed,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "reason": self.reason,
        }


def collect_diagnostics(
    project_root: Path,
    config: SafeCodeConfig | None = None,
    *,
    timeout_seconds: int = 8,
) -> list[DiagnosticCommandResult]:
    """Run applicable diagnostics and return bounded, redacted results."""
    root = project_root.resolve()
    cfg = config or SafeCodeConfig.load(root)
    results: list[DiagnosticCommandResult] = []
    for name, argv in _diagnostic_commands(root):
        results.append(_run_diagnostic(root, cfg, name, argv, timeout_seconds=timeout_seconds))
    return results


def diagnostics_context_block(project_root: Path, config: SafeCodeConfig | None = None) -> dict:
    """Return diagnostics as a model-context friendly dict."""
    results = collect_diagnostics(project_root, config)
    return {
        "summary": {
            "count": len(results),
            "failed": sum(1 for item in results if item.executed and item.exit_code != 0),
            "skipped": sum(1 for item in results if not item.executed),
        },
        "results": [item.as_context() for item in results],
    }


def _diagnostic_commands(root: Path) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    if (root / "tests").is_dir() and _has_files(root, "*.py"):
        commands.append(("pytest", ["python3", "-m", "pytest", "-q"]))
    elif _has_files(root, "*.py"):
        py_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py") if ".venv" not in p.parts)[:20]
        if py_files:
            commands.append(("py_compile", ["python3", "-m", "py_compile", *py_files]))
    if (root / "tsconfig.json").exists():
        commands.append(("tsc", ["tsc", "--noEmit"]))
    if (root / "go.mod").exists():
        commands.append(("go-test", ["go", "test", "./..."]))
    return commands[:3]


def _has_files(root: Path, pattern: str) -> bool:
    try:
        return any(path.is_file() for path in root.rglob(pattern))
    except OSError:
        return False


def _run_diagnostic(
    root: Path,
    config: SafeCodeConfig,
    name: str,
    argv: list[str],
    *,
    timeout_seconds: int,
) -> DiagnosticCommandResult:
    executable = argv[0]
    if _which(executable) is None:
        return DiagnosticCommandResult(
            name=name,
            command=argv,
            exit_code=127,
            output="",
            duration_ms=0,
            executed=False,
            reason=f"{executable!r} not found",
        )

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            env=ShellRunner(root, config)._sanitized_env(),
        )
        output = _bounded(redact_secrets((completed.stdout or "") + (completed.stderr or "")))
        return DiagnosticCommandResult(
            name=name,
            command=argv,
            exit_code=completed.returncode,
            output=output,
            duration_ms=int((time.perf_counter() - started) * 1000),
            executed=True,
        )
    except subprocess.TimeoutExpired as exc:
        output = _bounded(redact_secrets((exc.stdout or "") + (exc.stderr or "")))
        return DiagnosticCommandResult(
            name=name,
            command=argv,
            exit_code=124,
            output=output,
            duration_ms=int((time.perf_counter() - started) * 1000),
            executed=True,
            reason="diagnostic timed out",
        )
    except Exception as exc:
        return DiagnosticCommandResult(
            name=name,
            command=argv,
            exit_code=1,
            output="",
            duration_ms=int((time.perf_counter() - started) * 1000),
            executed=False,
            reason=f"{type(exc).__name__}: {exc}",
        )


def _which(executable: str) -> str | None:
    for directory in os.getenv("PATH", "").split(os.pathsep):
        candidate = Path(directory) / executable
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _bounded(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + "\n--- [diagnostic output truncated] ---"
