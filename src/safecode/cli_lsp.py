"""Terminal language-service commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.index.language_service import LanguageServiceManager


lsp_app = typer.Typer(help="[EXPERIMENTAL] Inspect terminal language services.")


@lsp_app.command("status")
def lsp_status(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show detected language services."""
    manager = LanguageServiceManager(Path.cwd())
    statuses = manager.status()
    data = [item.__dict__ for item in statuses]
    if json_output:
        print(render_json(CLIJSONResponse(command="lsp status", status="success", data={"services": data})))
        return

    table = Table(title="Language Services")
    table.add_column("Language")
    table.add_column("Available")
    table.add_column("Command")
    table.add_column("Reason")
    for item in statuses:
        table.add_row(item.language, "yes" if item.available else "no", item.command, item.reason)
    console.print(table)


@lsp_app.command("diagnostics")
def lsp_diagnostics(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Run available language diagnostics and normalize output."""
    manager = LanguageServiceManager(Path.cwd())
    diagnostics = manager.diagnostics()
    data = [item.__dict__ for item in diagnostics]
    if json_output:
        print(render_json(CLIJSONResponse(command="lsp diagnostics", status="success", data={"diagnostics": data})))
        return

    if not diagnostics:
        console.print("[green]No language diagnostics found, or no language service is available.[/green]")
        return
    table = Table(title="Language Diagnostics")
    table.add_column("Language")
    table.add_column("File")
    table.add_column("Line", justify="right")
    table.add_column("Rule")
    table.add_column("Message")
    for item in diagnostics:
        table.add_row(item.language, item.file, str(item.line), item.rule, item.message)
    console.print(table)
