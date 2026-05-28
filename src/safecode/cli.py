"""Command line entrypoint for SafeCode Agent."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig, ensure_config_file
from safecode.doctor import Doctor
from safecode.eval.cases import default_cases
from safecode.eval.runner import EvalRunner
from safecode.export.bundle import Exporter
from safecode.ide.manifest import render_manifest, write_manifest
from safecode.index.files import FileIndexer
from safecode.index.python_symbols import PythonSymbolIndexer
from safecode.mcp.discovery import MCPDiscovery
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.store import MemoryStore
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError
from safecode.project.rules import ProjectRules
from safecode.report.render import ReportRenderer
from safecode.release.checklist import render_release_checklist
from safecode.shell.risk import RiskLevel
from safecode.shell.runner import ShellRunner
from safecode.skills.loader import SkillLoader
from safecode.state.progress import ProgressState, ProgressStore
from safecode.subagents.task import SubagentTaskStore
from safecode.tools.registry import ToolRegistry
from safecode.queue.store import QueueStore
from safecode.utils.time import utc_now_iso

app = typer.Typer(
    name="sac",
    help="SafeCode Agent: safety-first terminal coding assistant.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage SafeCode project config.")
skills_app = typer.Typer(help="List and inspect skills.")
tools_app = typer.Typer(help="List internal tools.")
index_app = typer.Typer(help="Build lightweight project indexes.")
progress_app = typer.Typer(help="Read and update long-running progress.")
mcp_app = typer.Typer(help="Inspect configured MCP servers and tools.")
subagent_app = typer.Typer(help="Create file-backed subagent tasks.")
queue_app = typer.Typer(help="Manage a tiny local task queue.")
export_app = typer.Typer(help="Export SafeCode reports.")
ide_app = typer.Typer(help="Generate IDE adapter metadata.")
release_app = typer.Typer(help="Generate release helpers.")
logs_app = typer.Typer(help="Inspect runtime logs.")
console = Console()


def _runtime_logger() -> RuntimeLogger:
    """Return the runtime logger for the current project."""
    return RuntimeLogger(Path.cwd())


def _log_cli_error(component: str, message: str, exc: BaseException) -> None:
    """Persist CLI errors for later debugging."""
    _runtime_logger().error(component, message, exc=exc)


@app.callback()
def callback() -> None:
    """Keep Typer in multi-command mode."""


@app.command()
def ask(question: str) -> None:
    """Ask a read-only question about the current project."""
    project_root = Path.cwd()
    try:
        answer = AgentOrchestrator(project_root).ask(question)
    except Exception as exc:
        _log_cli_error("cli.ask", "ask command failed", exc)
        console.print(f"[red]Ask failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(answer)


@app.command()
def edit(task: str) -> None:
    """Create a pending patch proposal without modifying files."""
    project_root = Path.cwd()
    try:
        result = AgentOrchestrator(project_root).edit(task)
    except (PatchParseError, PatchValidationError) as exc:
        _log_cli_error("cli.edit", "patch proposal failed", exc)
        console.print(f"[red]Patch proposal failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _log_cli_error("cli.edit", "edit command failed", exc)
        console.print(f"[red]Edit failed:[/red] {exc}")
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
        _log_cli_error("cli.apply", "apply preview failed", exc)
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
        _log_cli_error("cli.apply", "apply command failed", exc)
        console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _log_cli_error("cli.apply", "apply command failed", exc)
        console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Applied patch {result.proposal.id}\n"
            f"Checkpoint: {result.checkpoint.checkpoint_id}\n"
            f"Hooks: {len(result.hooks.results) if result.hooks else 0}\n"
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
        _log_cli_error("cli.rollback", "rollback failed", exc)
        console.print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _log_cli_error("cli.rollback", "rollback failed", exc)
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


@app.command("run")
def run_command(command: str, yes: bool = typer.Option(False, "--yes", "-y", help="Approve medium/high risk commands.")) -> None:
    """Run a shell command through SafeCode risk checks."""
    project_root = Path.cwd()
    runner = ShellRunner(project_root)
    risk = runner.assess(command)
    console.print(Panel.fit("\n".join([f"Risk: {risk.level}", *risk.reasons]), title="Shell Risk"))

    approved = yes
    if risk.level == RiskLevel.MEDIUM and not yes:
        approved = typer.confirm("Run this medium-risk command?", default=False)
    if risk.level == RiskLevel.HIGH and not yes:
        console.print("[red]High-risk command blocked by policy.[/red]")
        approved = False
    elif risk.level == RiskLevel.HIGH and yes:
        console.print("[red]High-risk command remains blocked even with --yes.[/red]")

    result = runner.run(command, approved=approved)
    _runtime_logger().info(
        "cli.run",
        "shell command evaluated",
        command=command,
        exit_code=str(result.exit_code),
        executed=str(result.executed),
        risk=str(result.risk.level),
    )
    AgentOrchestrator(project_root).audit_logger.write(
        AuditEvent(
            type="shell_completed" if result.executed else "shell_blocked",
            timestamp=utc_now_iso(),
            status="success" if result.exit_code == 0 else "failed",
            command=command,
            exit_code=result.exit_code,
            message=f"risk={result.risk.level}; duration_ms={result.duration_ms}",
        )
    )
    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(f"[red]{result.stderr}[/red]")
    raise typer.Exit(code=0 if result.exit_code in (0, 125, 126) else result.exit_code)


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
def tools_list() -> None:
    """List built-in tools."""
    table = Table(title="SafeCode Tools")
    table.add_column("Name")
    table.add_column("Risk")
    table.add_column("Description")
    for tool in ToolRegistry().list():
        table.add_row(tool.name, tool.risk, tool.description)
    console.print(table)


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


@mcp_app.command("tools")
def mcp_tools() -> None:
    """List configured MCP tools."""
    tools = MCPDiscovery(Path.cwd()).list_tools()
    table = Table(title="MCP Tools")
    table.add_column("Server")
    table.add_column("Tool")
    table.add_column("Risk")
    for tool in tools:
        table.add_row(tool.server, tool.name, tool.risk)
    console.print(table if tools else "[yellow]No MCP tools configured.[/yellow]")


@subagent_app.command("create")
def subagent_create(title: str, instructions: str, write: bool = typer.Option(False, "--write")) -> None:
    """Create a file-backed subagent task."""
    task = SubagentTaskStore(Path.cwd()).create(title, instructions, readonly=not write)
    console.print(f"Subagent task created: {task.id}")


@app.command("rules")
def rules(init: bool = typer.Option(False, "--init")) -> None:
    """Show or initialize SAC.md project rules."""
    rules_store = ProjectRules(Path.cwd())
    if init:
        rules_store.ensure()
    console.print(rules_store.read() or "[yellow]No SAC.md found. Run sac rules --init.[/yellow]")


@app.command("memory")
def memory_set(key: str, value: str) -> None:
    """Remember a low-risk project fact."""
    MemoryStore(Path.cwd()).remember(key, value)
    console.print("[green]Memory updated.[/green]")


@app.command("report")
def report() -> None:
    """Render a Markdown report from recent audit events."""
    console.print(ReportRenderer(Path.cwd()).render_markdown())


@export_app.command("report")
def export_report(output: Path = typer.Option(Path(".sac/reports/latest.md"), "--output", "-o")) -> None:
    """Export a Markdown report to a file."""
    path = Exporter(Path.cwd()).report(output)
    console.print(f"Report exported: {path}")


@app.command("eval")
def eval_demo() -> None:
    """Run lightweight local eval cases."""
    results = EvalRunner(Path.cwd()).run(default_cases())
    table = Table(title="SafeCode Eval")
    table.add_column("Case")
    table.add_column("Passed")
    for result in results:
        table.add_row(result.name, "yes" if result.passed else "no")
    console.print(table)


@queue_app.command("add")
def queue_add(title: str) -> None:
    """Add a pending task to the local queue."""
    task = QueueStore(Path.cwd()).add(title)
    console.print(f"Queued task: {task.id}")


@queue_app.command("list")
def queue_list() -> None:
    """List queued tasks."""
    table = Table(title="SafeCode Queue")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Title")
    for task in QueueStore(Path.cwd()).list():
        table.add_row(task.id, task.status, task.title)
    console.print(table)


@queue_app.command("complete-next")
def queue_complete_next() -> None:
    """Mark the next pending task as completed."""
    task = QueueStore(Path.cwd()).complete_next()
    console.print(f"Completed task: {task.id}" if task else "[yellow]No pending tasks.[/yellow]")


@ide_app.command("manifest")
def ide_manifest(write: bool = typer.Option(False, "--write")) -> None:
    """Show or write an IDE command manifest."""
    if write:
        path = write_manifest(Path.cwd())
        console.print(f"IDE manifest written: {path}")
    else:
        console.print(Syntax(render_manifest(), "json", theme="ansi_dark"))


@release_app.command("checklist")
def release_checklist(version: str) -> None:
    """Render a release checklist."""
    console.print(render_release_checklist(version))


@app.command("doctor")
def doctor() -> None:
    """Check local install and project environment."""
    table = Table(title="SafeCode Doctor")
    table.add_column("Check")
    table.add_column("Passed")
    table.add_column("Detail")
    for check in Doctor(Path.cwd()).run():
        table.add_row(check.name, "yes" if check.passed else "no", check.detail)
    console.print(table)


@logs_app.command("show")
def logs_show(
    limit: int = typer.Option(20, "--limit", "-n"),
    level: str | None = typer.Option(None, "--level"),
    traceback_: bool = typer.Option(False, "--traceback", help="Show traceback text."),
) -> None:
    """Show recent structured runtime logs."""
    events = RuntimeLogger(Path.cwd()).read_recent(limit=limit, level=level)
    if not events:
        console.print("[yellow]No runtime logs found.[/yellow]")
        return

    table = Table(title="SafeCode Runtime Logs")
    table.add_column("Time")
    table.add_column("Level")
    table.add_column("Component")
    table.add_column("Message")
    table.add_column("Error")
    table.add_column("Details")
    for event in events:
        details = ", ".join(f"{key}={value}" for key, value in event.details.items())
        table.add_row(
            event.timestamp,
            event.level,
            event.component,
            event.message,
            event.error_type or "",
            details,
        )
        if traceback_ and event.traceback:
            table.add_row("", "", "", event.traceback, "", "")
    console.print(table)


app.add_typer(config_app, name="config")
app.add_typer(skills_app, name="skills")
app.add_typer(tools_app, name="tools")
app.add_typer(index_app, name="index")
app.add_typer(progress_app, name="progress")
app.add_typer(mcp_app, name="mcp")
app.add_typer(subagent_app, name="subagent")
app.add_typer(queue_app, name="queue")
app.add_typer(export_app, name="export")
app.add_typer(ide_app, name="ide")
app.add_typer(release_app, name="release")
app.add_typer(logs_app, name="logs")


def main() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    main()
