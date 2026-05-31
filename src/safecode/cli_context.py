"""Context debug commands for SafeCode Agent (v2.1.4)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from safecode.cli_shared import console, log_cli_error
from safecode.config import SafeCodeConfig

context_app = typer.Typer(help="Inspect context selection for a task (read-only, no LLM).")


@context_app.command("explain")
def context_explain(
    task: str = typer.Argument(..., help="Task description to explain context selection for."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    limit: int = typer.Option(10, "--limit", help="Maximum number of selected sources to show."),
) -> None:
    """Show which files and snippets would be selected for a task and why.

    Prints selected files with match reasons, budget metadata, and repo-map
    statistics. Read-only — does not call the LLM or write any files.
    """
    project_root = (root or Path.cwd()).resolve()
    try:
        config = SafeCodeConfig.load(project_root)
    except Exception as exc:
        log_cli_error("cli.context.explain", "failed to load config", exc)
        raise typer.Exit(1)

    # --- Selection explanation ---
    try:
        from safecode.context.selector import ContextSelector

        sources = ContextSelector(project_root).select_sources(task, limit=limit)
    except Exception as exc:
        log_cli_error("cli.context.explain", "context selection failed", exc)
        raise typer.Exit(1)

    console.rule("[bold blue]Context Selection[/bold blue]")
    if sources:
        table = Table(title=f"Selected sources for: {task!r}", show_lines=False)
        table.add_column("File", style="cyan", no_wrap=True)
        table.add_column("Score", justify="right")
        table.add_column("Reason")
        for source in sources:
            table.add_row(source.path, str(source.score), source.reason)
        console.print(table)
    else:
        console.print("[yellow]No files matched the task query.[/yellow]")

    # --- Budget metadata ---
    try:
        from safecode.context.budget import ContextBudget

        budget = ContextBudget.from_max_chars(config.max_context_chars)
        console.rule("[bold blue]Budget Metadata[/bold blue]")
        console.print(f"  Max bytes:   {budget.max_bytes:,}")
        console.print(f"  Max tokens:  {budget.max_tokens:,}" if budget.max_tokens else "  Max tokens:  n/a")
    except Exception as exc:
        log_cli_error("cli.context.explain", "budget metadata unavailable", exc)

    # --- Repo-map statistics ---
    try:
        from safecode.index.repo_map import RepoMapBuilder

        repo_map = RepoMapBuilder(project_root).build()
        console.rule("[bold blue]Repo Map[/bold blue]")
        rm_table = Table(show_header=True)
        rm_table.add_column("Section")
        rm_table.add_column("Count", justify="right")
        rm_table.add_row("Files", str(len(repo_map.files)))
        rm_table.add_row("Symbols", str(len(repo_map.symbols)))
        rm_table.add_row("Imports", str(len(repo_map.imports)))
        rm_table.add_row("Tests", str(len(repo_map.tests)))
        rm_table.add_row("Commands", str(len(repo_map.commands)))
        rm_table.add_row("Entrypoints", str(len(repo_map.entrypoints)))
        console.print(rm_table)
    except Exception as exc:
        log_cli_error("cli.context.explain", "repo map unavailable", exc)
