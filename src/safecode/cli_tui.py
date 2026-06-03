from pathlib import Path

import typer

from safecode.cli_shared import console
from safecode.tui.dashboard import render_dashboard

tui_app = typer.Typer(help="Open compact terminal UI views.")


@tui_app.command("dashboard")
def tui_dashboard(history_limit: int = typer.Option(8, "--history-limit", "-n", min=1)) -> None:
    """Show plan, approval, diff, command output, and history context."""
    console.print(render_dashboard(Path.cwd(), history_limit=history_limit))


@tui_app.command("interactive")
def tui_interactive(
    refresh: float = typer.Option(2.0, "--refresh", help="Refresh interval in seconds (TTY only)."),
    history_limit: int = typer.Option(8, "--history-limit", "-n", min=1),
) -> None:
    """[EXPERIMENTAL] Interactive TUI: session list, plan, pending diff, journal tail.

    In non-TTY mode (piped output), prints a static snapshot and exits 0.
    In TTY mode, refreshes every --refresh seconds; press Ctrl+C to exit.
    """
    from safecode.tui.interactive import run_interactive

    run_interactive(Path.cwd(), refresh_seconds=refresh, history_limit=history_limit)
