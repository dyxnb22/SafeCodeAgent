"""Formatter workflow command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.config import SafeCodeConfig
from safecode.project.formatter import detect_formatters, run_formatters


format_app = typer.Typer(help="[EXPERIMENTAL] Detect and run project formatters.")


@format_app.command("run")
def format_run(
    check: bool = typer.Option(False, "--check", help="Run formatter check mode when available."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve formatter command execution."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Run detected or configured formatters through SafeCode command policy."""
    project_root = Path.cwd()
    config = SafeCodeConfig.load(project_root)
    detected = detect_formatters(project_root, config)
    if not detected:
        data = {"formatters": [], "results": [], "status": "skipped", "reason": "no_formatter_detected"}
        if json_output:
            print(render_json(CLIJSONResponse(command="format run", status="success", data=data)))
        else:
            console.print("[yellow]No formatter detected.[/yellow]")
        return

    results = run_formatters(project_root, check=check, approved=yes, config=config)
    data = {
        "formatters": [item.name for item in detected],
        "results": [
            {
                "formatter": item.formatter,
                "command": list(item.command),
                "exit_code": item.exit_code,
                "executed": item.executed,
            }
            for item in results
        ],
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="format run", status="success", data=data)))
        return

    table = Table(title="Formatter Results")
    table.add_column("Formatter")
    table.add_column("Command")
    table.add_column("Executed")
    table.add_column("Exit", justify="right")
    for item in results:
        table.add_row(item.formatter, " ".join(item.command), "yes" if item.executed else "no", str(item.exit_code))
    console.print(table)
