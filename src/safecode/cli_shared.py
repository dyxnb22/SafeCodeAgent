"""Shared CLI rendering and runtime helpers."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from safecode.logs.runtime import RuntimeLogger

console = Console()


def show_human_checkpoint(checkpoint) -> None:
    """Render a standardized human checkpoint."""
    lines = [
        f"Type: {checkpoint.checkpoint_type}",
        f"Risk: {checkpoint.risk_level}",
        f"Subject: {checkpoint.subject_hash}",
        "",
        checkpoint.summary,
    ]
    console.print(Panel.fit("\n".join(lines), title=checkpoint.title))


def runtime_logger() -> RuntimeLogger:
    """Return the runtime logger for the current project."""
    return RuntimeLogger(Path.cwd())


def log_cli_error(component: str, message: str, exc: BaseException) -> None:
    """Persist CLI errors for later debugging."""
    runtime_logger().error(component, message, exc=exc)
