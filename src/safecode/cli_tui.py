from pathlib import Path

import typer

from safecode.cli_shared import console
from safecode.tui.dashboard import render_dashboard

tui_app = typer.Typer(help="Open compact terminal UI views.")


@tui_app.command("dashboard")
def tui_dashboard(history_limit: int = typer.Option(8, "--history-limit", "-n", min=1)) -> None:
    """Show plan, approval, diff, command output, and history context."""
    console.print(render_dashboard(Path.cwd(), history_limit=history_limit))
