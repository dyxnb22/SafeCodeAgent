from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint

from safecode.config import SafeCodeConfig, ensure_config_file
from safecode.index.files import FileIndexer
from safecode.index.python_symbols import PythonSymbolIndexer
from safecode.index.repo_map import RepoMapBuilder
from safecode.skills.loader import SkillLoader
from safecode.state.progress import ProgressState, ProgressStore
from safecode.tools.registry import PermissionCategory, ToolRegistry, ToolRiskLevel

config_app = typer.Typer(help="Manage SafeCode project config.")
skills_app = typer.Typer(help="List and inspect skills.")
tools_app = typer.Typer(help="List and inspect internal tool schemas.")
index_app = typer.Typer(help="Build lightweight project indexes.")
progress_app = typer.Typer(help="Read and update long-running progress.")


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


@skills_app.command("list")
def skills_list() -> None:
    """List local skills."""
    skills = SkillLoader(Path.cwd()).list()
    table = Table(title="SafeCode Skills")
    table.add_column("Name")
    table.add_column("Path")
    for skill in skills:
        table.add_row(skill.name, str(skill.path))
    console.print(table if skills else "[yellow]No skills found.[/yellow]")


@skills_app.command("show")
def skills_show(name: str) -> None:
    """Show one skill."""
    skill = SkillLoader(Path.cwd()).get(name)
    console.print(Panel(skill.instructions, title=skill.name))


@tools_app.command("list")
def tools_list(
    risk: Optional[str] = typer.Option(None, "--risk", help="Filter by risk level (low, medium, high)."),
    permission: Optional[str] = typer.Option(None, "--permission", help="Filter by permission category."),
) -> None:
    """List built-in tool schemas with risk and permission metadata."""
    registry = ToolRegistry()
    tools = registry.list()

    if risk:
        try:
            risk_level = ToolRiskLevel(risk.lower())
        except ValueError:
            console.print(f"[red]Unknown risk level: {risk!r}. Use low, medium, or high.[/red]")
            raise typer.Exit(1)
        tools = [t for t in tools if t.risk == risk_level]

    if permission:
        try:
            perm_cat = PermissionCategory(permission.lower())
        except ValueError:
            valid = ", ".join(c.value for c in PermissionCategory)
            console.print(f"[red]Unknown permission category: {permission!r}. Use one of: {valid}[/red]")
            raise typer.Exit(1)
        tools = [t for t in tools if t.permission_category == perm_cat]

    table = Table(title="SafeCode Internal Tools")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Risk")
    table.add_column("Permission")
    table.add_column("Approval", justify="center")
    table.add_column("Description")
    for tool in tools:
        approval_marker = "[yellow]yes[/yellow]" if tool.requires_human_approval else "[green]no[/green]"
        table.add_row(tool.name, tool.risk, tool.permission_category, approval_marker, tool.description)
    console.print(table if tools else "[yellow]No tools match the given filters.[/yellow]")


@tools_app.command("inspect")
def tools_inspect(name: str = typer.Argument(..., help="Tool name to inspect.")) -> None:
    """Show full schema for a single tool including arguments and audit event."""
    registry = ToolRegistry()
    try:
        tool = registry.get(name)
    except KeyError:
        console.print(f"[red]Unknown tool: {name!r}[/red]")
        console.print(f"Available tools: {', '.join(registry.names())}")
        raise typer.Exit(1)

    from rich.panel import Panel as _Panel

    approval_text = "[yellow]required[/yellow]" if tool.requires_human_approval else "[green]not required[/green]"
    lines = [
        f"[bold]Description:[/bold] {tool.description}",
        f"[bold]Risk:[/bold]        {tool.risk}",
        f"[bold]Permission:[/bold]  {tool.permission_category}",
        f"[bold]Approval:[/bold]    {approval_text}",
    ]
    if tool.args:
        lines.append("\n[bold]Arguments:[/bold]")
        for arg in tool.args:
            req = "required" if arg.required else "optional"
            lines.append(f"  • {arg.name} ({arg.type}, {req}): {arg.description}")
    else:
        lines.append("\n[bold]Arguments:[/bold] none")
    if tool.audit_event:
        lines.append(f"\n[bold]Audit Event:[/bold] {tool.audit_event.event_type} — {tool.audit_event.description}")
    else:
        lines.append("\n[bold]Audit Event:[/bold] none")

    console.print(_Panel("\n".join(lines), title=f"[bold cyan]{tool.name}[/bold cyan]", expand=False))


@index_app.command("files")
def index_files() -> None:
    """List indexed files."""
    for item in FileIndexer(Path.cwd()).index():
        console.print(item.path)


@index_app.command("symbols")
def index_symbols() -> None:
    """List indexed Python symbols."""
    table = Table(title="Python Symbols")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Location")
    for symbol in PythonSymbolIndexer(Path.cwd()).index():
        table.add_row(symbol.kind, symbol.name, f"{symbol.path}:{symbol.line}")
    console.print(table)


@index_app.command("map")
def index_map(as_json: bool = typer.Option(False, "--json", help="Render full repo map as JSON.")) -> None:
    """Build a repo map with files, symbols, imports, tests, commands, and entrypoints."""
    repo_map = RepoMapBuilder(Path.cwd()).build()
    if as_json:
        console.print(Syntax(repo_map.to_json(), "json", theme="ansi_dark"))
        return

    summary = Table(title="SafeCode Repo Map")
    summary.add_column("Section")
    summary.add_column("Count")
    summary.add_row("Files", str(len(repo_map.files)))
    summary.add_row("Symbols", str(len(repo_map.symbols)))
    summary.add_row("Imports", str(len(repo_map.imports)))
    summary.add_row("Tests", str(len(repo_map.tests)))
    summary.add_row("Commands", str(len(repo_map.commands)))
    summary.add_row("Entrypoints", str(len(repo_map.entrypoints)))
    console.print(summary)

    if repo_map.entrypoints:
        entrypoints = Table(title="Entrypoints")
        entrypoints.add_column("Kind")
        entrypoints.add_column("Name")
        entrypoints.add_column("Target")
        for item in repo_map.entrypoints:
            location = item.path if item.line is None else f"{item.path}:{item.line}"
            entrypoints.add_row(item.kind, item.name, f"{item.target} ({location})")
        console.print(entrypoints)

    if repo_map.commands:
        commands = Table(title="Detected Commands")
        commands.add_column("Command")
        commands.add_column("Tool")
        commands.add_column("Confidence")
        for item in repo_map.commands:
            commands.add_row(item.command, item.tool, item.confidence)
        console.print(commands)


@progress_app.command("init")
def progress_init() -> None:
    """Create .sac/progress.md."""
    path = ProgressStore(Path.cwd()).ensure()
    console.print(f"Progress ready: {path}")


@progress_app.command("show")
def progress_show() -> None:
    """Show progress Markdown."""
    console.print(ProgressStore(Path.cwd()).read_text())


@progress_app.command("set")
def progress_set(goal: str, next_step: str = typer.Option("", "--next")) -> None:
    """Set a simple progress goal and optional next step."""
    state = ProgressState(goal=goal, completed=[], next_steps=[next_step] if next_step else [], blockers=[])
    ProgressStore(Path.cwd()).write(state)
    console.print("[green]Progress updated.[/green]")


