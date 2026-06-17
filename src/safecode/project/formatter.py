"""Project formatter detection and execution."""

from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.shell.runner import ShellRunner, ShellRunResult


@dataclass(frozen=True)
class FormatterCommand:
    name: str
    command: tuple[str, ...]
    check_command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FormatterRun:
    formatter: str
    command: tuple[str, ...]
    exit_code: int
    executed: bool
    stdout: str = ""
    stderr: str = ""


def detect_formatters(project_root: Path, config: SafeCodeConfig | None = None) -> list[FormatterCommand]:
    """Return formatter commands suitable for the current project."""
    config = config or SafeCodeConfig.load(project_root)
    if config.formatter.commands:
        return [
            FormatterCommand(f"configured-{index + 1}", tuple(shlex.split(command)))
            for index, command in enumerate(config.formatter.commands)
            if command.strip()
        ]

    commands: list[FormatterCommand] = []
    if (project_root / "pyproject.toml").exists():
        if shutil.which("ruff"):
            commands.append(FormatterCommand("ruff", ("ruff", "format", "."), ("ruff", "format", "--check", ".")))
        elif shutil.which("black"):
            commands.append(FormatterCommand("black", ("black", "."), ("black", "--check", ".")))
    if (project_root / "package.json").exists() and shutil.which("prettier"):
        commands.append(FormatterCommand("prettier", ("prettier", "--write", "."), ("prettier", "--check", ".")))
    if (project_root / "go.mod").exists() and shutil.which("gofmt"):
        commands.append(FormatterCommand("gofmt", ("gofmt", "-w", "."), None))
    if (project_root / "Cargo.toml").exists() and shutil.which("cargo"):
        commands.append(FormatterCommand("cargo-fmt", ("cargo", "fmt"), ("cargo", "fmt", "--check")))
    return commands


def run_formatters(
    project_root: Path,
    *,
    check: bool = False,
    approved: bool = False,
    config: SafeCodeConfig | None = None,
    shell_runner: ShellRunner | None = None,
) -> list[FormatterRun]:
    """Run detected formatters through ShellRunner."""
    config = config or SafeCodeConfig.load(project_root)
    runner = shell_runner or ShellRunner(project_root, config)
    results: list[FormatterRun] = []
    for formatter in detect_formatters(project_root, config):
        command = formatter.check_command if check and formatter.check_command else formatter.command
        result: ShellRunResult = runner.run(shlex.join(command), approved=approved)
        results.append(
            FormatterRun(
                formatter=formatter.name,
                command=command,
                exit_code=result.exit_code,
                executed=result.executed,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        )
    return results
