"""Command line entrypoint for SafeCode Agent."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.config import SafeCodeConfig, ensure_config_file
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError

app = typer.Typer(
    name="sac",
    help="SafeCode Agent: safety-first terminal coding assistant.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage SafeCode project config.")
console = Console()


@app.callback()
def callback() -> None:
    """Keep Typer in multi-command mode."""


@app.command()
def ask(question: str) -> None:
    """Ask a read-only question about the current project."""
    project_root = Path.cwd()
    answer = AgentOrchestrator(project_root).ask(question)
    console.print(answer)


@app.command()
def edit(task: str) -> None:
    """Create a pending patch proposal without modifying files."""
    project_root = Path.cwd()
    try:
        result = AgentOrchestrator(project_root).edit(task)
    except (PatchParseError, PatchValidationError) as exc:
        console.print(f"[red]Patch proposal failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(Panel.fit(f"Pending patch saved: {result.pending_patch_path}", title="SafeCode"))
    console.print(Syntax(result.diff_text, "diff", theme="ansi_dark"))


@app.command()
def apply() -> None:
    """Apply the latest pending patch after review."""
    project_root = Path.cwd()
    orchestrator = AgentOrchestrator(project_root)

    try:
        preview = orchestrator.preview_apply()
    except (FileNotFoundError, PatchValidationError) as exc:
        console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(Syntax(preview.diff_text, "diff", theme="ansi_dark"))
    approved = typer.confirm("Apply this patch?", default=False)
    if not approved:
        console.print("[yellow]Patch was not applied.[/yellow]")
        raise typer.Exit(code=0)

    try:
        result = orchestrator.apply(preview.proposal)
    except PatchValidationError as exc:
        console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Applied patch {result.proposal.id}\n"
            f"Checkpoint: {result.checkpoint.checkpoint_id}\n"
            f"Files: {', '.join(result.files)}",
            title="SafeCode",
        )
    )


@app.command()
def rollback(last: bool = typer.Option(False, "--last", help="Rollback the latest checkpoint.")) -> None:
    """Rollback a previous applied patch."""
    if not last:
        console.print("[red]Only --last is planned for v0.1.[/red]")
        raise typer.Exit(code=1)

    project_root = Path.cwd()
    try:
        result = AgentOrchestrator(project_root).rollback_last()
    except FileNotFoundError as exc:
        console.print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Rolled back checkpoint: {result.checkpoint.checkpoint_id}\n"
            f"Files: {', '.join(result.files)}",
            title="SafeCode",
        )
    )


@app.command()
def history() -> None:
    """Show recent SafeCode Agent audit events."""
    events = AgentOrchestrator(Path.cwd()).history()
    if not events:
        console.print("[yellow]No audit events found.[/yellow]")
        return

    table = Table(title="SafeCode History")
    table.add_column("Time")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Patch")
    table.add_column("Checkpoint")
    table.add_column("Files")
    table.add_column("Message")

    for event in events:
        table.add_row(
            event.timestamp,
            event.type,
            event.status,
            event.patch_id or "",
            event.checkpoint_id or "",
            ", ".join(event.files),
            event.message or "",
        )

    console.print(table)


@config_app.command("init")
def config_init() -> None:
    """Create .sac/config.toml."""
    path = ensure_config_file(Path.cwd())
    console.print(f"Config ready: {path}")


@config_app.command("show")
def config_show() -> None:
    """Show effective SafeCode config."""
    config = SafeCodeConfig.load(Path.cwd())
    console.print(Syntax(config.to_toml(), "toml", theme="ansi_dark"))


app.add_typer(config_app, name="config")


def main() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    main()
