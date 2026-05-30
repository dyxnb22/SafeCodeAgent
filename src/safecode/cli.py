"""Command line entrypoint for SafeCode Agent."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig, ensure_config_file
from safecode.doctor import Doctor
from safecode.eval.cases import default_cases
from safecode.eval.runner import EvalRunner
from safecode.export.bundle import Exporter
from safecode.hooks.approvals import HookApprovalStore
from safecode.ide.manifest import render_manifest, write_manifest
from safecode.index.files import FileIndexer
from safecode.index.python_symbols import PythonSymbolIndexer
from safecode.mcp.discovery import MCPDiscovery
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.mcp.proposal import MCPWriteProposalStore
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.store import MemoryStore
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError
from safecode.project.rules import ProjectRules
from safecode.report.render import ReportRenderer
from safecode.release.checklist import render_release_checklist
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.execution import (
    SandboxExecutionGate,
    SandboxExecutionProposalStore,
    SandboxExecutionResultStore,
)
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.preflight import SandboxExecutionPreflight
from safecode.sandbox.planner import SandboxPlanner
from safecode.shell.risk import RiskLevel
from safecode.shell.runner import ShellRunner
from safecode.skills.loader import SkillLoader
from safecode.state.progress import ProgressState, ProgressStore
from safecode.subagents.task import SubagentTaskStore
from safecode.subagents.runner import ReadonlySubagentRunner
from safecode.subagents.merge import SubagentMergeReviewer
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
audit_app = typer.Typer(help="Inspect and verify audit logs.")
hooks_app = typer.Typer(help="Approve and inspect project hooks.")
sandbox_app = typer.Typer(help="Check OS sandbox capabilities and recommendations.")
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


@mcp_app.command("call-readonly")
def mcp_call_readonly(
    server: str,
    tool: str,
    input_json: str = typer.Option("{}", "--input", help="JSON input for the MCP tool."),
) -> None:
    """Invoke a read-only MCP tool."""
    project_root = Path.cwd()
    try:
        payload = json.loads(input_json) if input_json else {}
    except json.JSONDecodeError as exc:
        _log_cli_error("cli.mcp.call_readonly", "invalid MCP input JSON", exc)
        console.print(f"[red]Invalid JSON input:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        console.print("[red]MCP input must be a JSON object.[/red]")
        raise typer.Exit(code=1)
    result = MCPReadOnlyRunner(project_root).call_readonly(server, tool, payload)
    if result.output:
        console.print(result.output)
    if result.error:
        console.print(f"[red]{result.error}[/red]")
    raise typer.Exit(code=0 if result.exit_code == 0 else result.exit_code)


@mcp_app.command("propose-write")
def mcp_propose_write(
    server: str,
    tool: str,
    input_json: str = typer.Option("{}", "--input", help="JSON input for the MCP write tool."),
) -> None:
    """Create a pending MCP write proposal without executing."""
    project_root = Path.cwd()
    try:
        payload = json.loads(input_json) if input_json else {}
    except json.JSONDecodeError as exc:
        _log_cli_error("cli.mcp.propose_write", "invalid MCP input JSON", exc)
        console.print(f"[red]Invalid JSON input:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        console.print("[red]MCP input must be a JSON object.[/red]")
        raise typer.Exit(code=1)

    runner = MCPReadOnlyRunner(project_root)
    try:
        proposal = runner.propose_write(server, tool, payload)
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=0) from exc
    except PermissionError as exc:
        console.print(f"[red]Blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except FileExistsError as exc:
        console.print(f"[red]Blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Proposal ID: {proposal.proposal_id}\n"
            f"Server: {proposal.server}\n"
            f"Tool: {proposal.tool}\n"
            f"Classification: {proposal.classification}\n"
            f"Risk Level: {proposal.risk_level}\n"
            f"Status: {proposal.status}\n"
            f"Pending path: .sac/pending_mcp_call.json",
            title="MCP Write Proposal",
        )
    )


@mcp_app.command("pending")
def mcp_pending() -> None:
    """Show the pending MCP write proposal."""
    project_root = Path.cwd()
    store = MCPWriteProposalStore(project_root)
    proposal = store.load_pending()

    if proposal is None:
        console.print("[yellow]No pending MCP write proposal.[/yellow]")
        return

    table = Table(title="Pending MCP Write Proposal")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Proposal ID", proposal.proposal_id)
    table.add_row("Server", proposal.server)
    table.add_row("Tool", proposal.tool)
    table.add_row("Classification", proposal.classification)
    table.add_row("Risk Level", proposal.risk_level)
    table.add_row("Status", proposal.status)
    table.add_row("Created At", proposal.created_at)
    table.add_row("Reason", proposal.reason)
    table.add_row("Input Hash", proposal.input_hash)
    console.print(table)


@mcp_app.command("discard")
def mcp_discard() -> None:
    """Discard the pending MCP write proposal."""
    project_root = Path.cwd()
    store = MCPWriteProposalStore(project_root)

    if not store.pending_path.exists():
        console.print("[yellow]No pending MCP write proposal to discard.[/yellow]")
        return

    proposal = store.load_pending()
    store.discard_pending()
    audit_logger = AuditLogger(project_root)
    metadata = {}
    if proposal is not None:
        metadata = {
            "proposal_id": proposal.proposal_id,
            "server": proposal.server,
            "tool": proposal.tool,
            "classification": proposal.classification,
        }
    audit_logger.write(
        AuditEvent(
            type="mcp_write_discarded",
            timestamp=utc_now_iso(),
            status="success",
            message="Pending MCP write proposal discarded.",
            metadata=metadata,
        )
    )
    console.print("[green]Pending MCP write proposal discarded.[/green]")


@subagent_app.command("create")
def subagent_create(title: str, instructions: str, write: bool = typer.Option(False, "--write")) -> None:
    """Create a file-backed subagent task."""
    task = SubagentTaskStore(Path.cwd()).create(title, instructions, readonly=not write)
    console.print(f"Subagent task created: {task.id}")


@subagent_app.command("run-readonly")
def subagent_run_readonly(
    title: str,
    instructions: str,
) -> None:
    """Run a read-only subagent task that writes only a result file."""
    project_root = Path.cwd()
    try:
        result = ReadonlySubagentRunner(project_root).run(title, instructions)
    except Exception as exc:
        _log_cli_error("cli.subagent.run_readonly", "subagent run failed", exc)
        console.print(f"[red]Subagent run failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Task ID: {result.task.id}\n"
            f"Status: {result.task.status}\n"
            f"Result: {result.result_path}",
            title="Subagent Read-only Run",
        )
    )


@subagent_app.command("list")
def subagent_list() -> None:
    """List subagent tasks."""
    project_root = Path.cwd()
    tasks = SubagentTaskStore(project_root).list_tasks()

    if not tasks:
        console.print("[yellow]No subagent tasks found.[/yellow]")
        return

    table = Table(title="Subagent Tasks")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Readonly")
    table.add_column("Created")
    for task in tasks:
        table.add_row(
            task.id,
            task.title[:60],
            task.status,
            "yes" if task.readonly else "no",
            task.created_at[:19],
        )
    console.print(table)


@subagent_app.command("show")
def subagent_show(task_id: str) -> None:
    """Show a subagent task and its result."""
    project_root = Path.cwd()
    store = SubagentTaskStore(project_root)
    task = store.get_task(task_id)

    if task is None:
        console.print(f"[red]Subagent task not found: {task_id}[/red]")
        raise typer.Exit(code=1)

    table = Table(title=f"Subagent Task: {task.id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("ID", task.id)
    table.add_row("Title", task.title)
    table.add_row("Instructions", task.instructions[:120])
    table.add_row("Readonly", "yes" if task.readonly else "no")
    table.add_row("Status", task.status)
    table.add_row("Created", task.created_at)
    if task.started_at:
        table.add_row("Started", task.started_at)
    if task.completed_at:
        table.add_row("Completed", task.completed_at)
    if task.result_path:
        table.add_row("Result Path", task.result_path)
    if task.error:
        table.add_row("Error", task.error)
    console.print(table)

    result_path = store.result_path_for(task.id)
    if result_path.exists():
        console.print(f"\n[bold]Result file:[/bold] {result_path}")
        console.print(result_path.read_text(encoding="utf-8")[:500])
    else:
        console.print("\n[yellow]No result file yet.[/yellow]")


@subagent_app.command("merge-review")
def subagent_merge_review(
    task_ids: list[str] = typer.Argument(..., help="Completed subagent task IDs to merge."),
    target: str = typer.Option("SUBAGENT_REVIEW.md", "--target", "-t", help="Target markdown file with merge marker."),
) -> None:
    """Create a pending patch proposal from completed subagent results."""
    project_root = Path.cwd()

    try:
        result = SubagentMergeReviewer(project_root).propose(task_ids, target)
    except (FileNotFoundError, ValueError, PermissionError, FileExistsError) as exc:
        _log_cli_error("cli.subagent.merge_review", "merge review blocked", exc)
        console.print(f"[red]Merge review blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _log_cli_error("cli.subagent.merge_review", "merge review failed", exc)
        console.print(f"[red]Merge review failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Patch ID: {result.proposal.id}\n"
            f"Tasks merged: {len(task_ids)}\n"
            f"Target: {target}\n"
            f"Pending patch: {result.pending_path}",
            title="Subagent Merge Review",
        )
    )
    console.print(Syntax(result.diff_text, "diff", theme="ansi_dark"))
    console.print("[green]Review the diff above. Run 'sac apply' to apply the merge.[/green]")


@sandbox_app.command("status")
def sandbox_status() -> None:
    """Show available sandbox backends and recommendations."""
    project_root = Path.cwd()
    plan = SandboxPlanner(project_root).plan()

    cap_table = Table(title="Sandbox Backend Status")
    cap_table.add_column("Backend")
    cap_table.add_column("Available")
    cap_table.add_column("Platforms")
    cap_table.add_column("Recommended For")
    for cap in plan.capabilities:
        cap_table.add_row(
            cap.backend.value,
            "[green]yes[/green]" if cap.available else "[red]no[/red]",
            ", ".join(cap.supported_platforms),
            cap.recommended_for or "-",
        )
    console.print(cap_table)

    console.print(
        Panel.fit(
            f"Platform: {plan.platform}\n"
            f"Recommended: [bold]{plan.recommended_backend.value}[/bold]",
            title="Recommendation",
        )
    )

    info = []
    for cap in plan.capabilities:
        if cap.backend == plan.recommended_backend:
            info.append(f"[bold]Recommended: {cap.backend.value}[/bold]")
            info.append(f"  {cap.reason}")
            if cap.limitations:
                info.append("  Limitations:")
                for limit in cap.limitations:
                    info.append(f"    - {limit}")

    if info:
        console.print(Panel("\n".join(info), title="Recommended Backend Details"))

    notes_lines = plan.notes + [
        "",
        "Active logical boundaries: " + ", ".join(plan.active_logical_boundaries),
    ]
    console.print(Panel("\n".join(notes_lines), title="Notes"))

    # v1.8.4: execution result summary
    result_store = SandboxExecutionResultStore(project_root)
    all_results = result_store.list_all()
    if all_results:
        completed = sum(1 for r in all_results if r.status == "completed")
        blocked_claim = sum(1 for r in all_results if r.status == "blocked_claim")
        latest = all_results[0]
        exit_str = str(latest.exit_code) if latest.exit_code is not None else "-"
        summary_lines = [
            f"Total: {len(all_results)}",
            f"Completed: {completed}",
            f"Blocked claims: {blocked_claim}",
            f"Latest: {latest.proposal_id[:12]}... [{latest.status}] exit={exit_str} ({latest.attempted_at[:19]})",
        ]
        console.print(Panel("\n".join(summary_lines), title="Execution Results"))


@sandbox_app.command("plan")
def sandbox_plan(
    command: list[str] = typer.Argument(..., help="Command to plan sandbox execution for."),
    purpose: str = typer.Option("shell", "--purpose", help="Purpose: shell, mcp, or hook."),
    allow_network: bool = typer.Option(False, "--allow-network", help="Request network access."),
    readonly_fs: bool = typer.Option(True, "--readonly-fs / --no-readonly-fs", help="Read-only filesystem."),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds."),
) -> None:
    """Generate a sandbox execution plan without executing the command."""
    project_root = Path.cwd()
    config = SafeCodeConfig.load(project_root)

    try:
        exec_plan = SandboxAdapterFactory(project_root, config).create_plan(
            command=command,
            purpose=purpose,
            allow_network=allow_network,
            readonly_filesystem=readonly_fs,
            timeout_seconds=timeout,
        )
    except PermissionError as exc:
        console.print(f"[red]Sandbox plan blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Sandbox Execution Plan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Backend", exec_plan.backend.value)
    table.add_row("Command", " ".join(exec_plan.command))
    table.add_row("CWD", exec_plan.cwd)
    table.add_row("Network", "[green]enabled[/green]" if exec_plan.network_enabled else "[red]disabled[/red]")
    table.add_row("Readonly FS", "[green]yes[/green]" if exec_plan.readonly_filesystem else "[yellow]no[/yellow]")
    table.add_row("Writable Paths", ", ".join(exec_plan.writable_paths) if exec_plan.writable_paths else "(none)")
    table.add_row("Env Keys", ", ".join(exec_plan.env_keys) if exec_plan.env_keys else "(none)")
    table.add_row("Timeout", f"{exec_plan.timeout_seconds}s")
    table.add_row("Dry Run", "[bold yellow]true[/bold yellow]")
    console.print(table)

    if exec_plan.warnings:
        warn_lines = [f"- {w}" for w in exec_plan.warnings]
        console.print(Panel("\n".join(warn_lines), title="[yellow]Warnings[/yellow]"))

    if exec_plan.limitations:
        limit_lines = [f"- {lim}" for lim in exec_plan.limitations]
        console.print(Panel("\n".join(limit_lines), title="[dim]Limitations[/dim]"))

    if exec_plan.profile_preview:
        console.print(
            Panel.fit(
                "[bold]Profile generated for preview only.[/bold]\n"
                "sandbox-exec was NOT executed.",
                title="Profile Preview",
            )
        )
        console.print(Syntax(exec_plan.profile_preview, "scheme", theme="ansi_dark", line_numbers=False))
        if exec_plan.profile_warnings:
            pw_lines = [f"- {w}" for w in exec_plan.profile_warnings]
            console.print(Panel("\n".join(pw_lines), title="[yellow]Profile Warnings[/yellow]"))

    if exec_plan.args_preview:
        console.print(
            Panel.fit(
                "[bold]Args generated for preview only.[/bold]\n"
                "bwrap was NOT executed.",
                title="Bwrap Args Preview",
            )
        )
        arg_table = Table(title="bwrap argv")
        arg_table.add_column("Index")
        arg_table.add_column("Argument")
        for i, arg in enumerate(exec_plan.args_preview):
            arg_table.add_row(str(i), arg)
        console.print(arg_table)
        if exec_plan.args_warnings:
            aw_lines = [f"- {w}" for w in exec_plan.args_warnings]
            console.print(Panel("\n".join(aw_lines), title="[yellow]Args Warnings[/yellow]"))

    if exec_plan.container_preview:
        console.print(
            Panel.fit(
                "[bold]Docker args generated for preview only.[/bold]\n"
                "docker was NOT executed.",
                title="Docker Container Preview",
            )
        )
        c_table = Table(title="docker run argv")
        c_table.add_column("Index")
        c_table.add_column("Argument")
        for i, arg in enumerate(exec_plan.container_preview):
            c_table.add_row(str(i), arg)
        console.print(c_table)
        if exec_plan.container_warnings:
            cw_lines = [f"- {w}" for w in exec_plan.container_warnings]
            console.print(Panel("\n".join(cw_lines), title="[yellow]Container Warnings[/yellow]"))
        if exec_plan.container_limitations:
            cl_lines = [f"- {lim}" for lim in exec_plan.container_limitations]
            console.print(Panel("\n".join(cl_lines), title="[dim]Container Limitations[/dim]"))

    console.print(
        Panel.fit(
            "[bold yellow]This command was NOT executed.[/bold yellow]\n"
            "v1.7.x generates sandbox execution plans and backend previews only.\n"
            "Actual OS-level sandbox execution is deferred to a future version.",
            title="Dry Run",
        )
    )


@sandbox_app.command("propose")
def sandbox_propose(
    command: list[str] = typer.Argument(..., help="Command to propose for sandbox execution."),
    purpose: str = typer.Option("shell", "--purpose"),
    allow_network: bool = typer.Option(False, "--allow-network"),
    readonly_fs: bool = typer.Option(True, "--readonly-fs / --no-readonly-fs"),
    timeout: int = typer.Option(30, "--timeout"),
) -> None:
    """Create a pending sandbox execution proposal. Does NOT execute."""
    project_root = Path.cwd()
    config = SafeCodeConfig.load(project_root)

    try:
        plan = SandboxAdapterFactory(project_root, config).create_plan(
            command=command,
            purpose=purpose,
            allow_network=allow_network,
            readonly_filesystem=readonly_fs,
            timeout_seconds=timeout,
        )
    except PermissionError as exc:
        console.print(f"[red]Sandbox proposal blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    gate = SandboxExecutionGate(project_root, config)
    try:
        proposal = gate.propose(plan, purpose)
    except FileExistsError as exc:
        console.print(f"[red]Proposal blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Proposal ID: {proposal.proposal_id}\n"
            f"Backend: {proposal.backend}\n"
            f"Command: {' '.join(proposal.command)}\n"
            f"Preview Kind: {proposal.preview_kind}\n"
            f"Pending path: .sac/pending_sandbox_execution.json",
            title="Sandbox Execution Proposal",
        )
    )
    console.print("[yellow]No command was executed.[/yellow]")


@sandbox_app.command("pending")
def sandbox_pending() -> None:
    """Show the pending sandbox execution proposal."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)
    proposal = gate.load_pending()

    if proposal is None:
        console.print("[yellow]No pending sandbox execution proposal.[/yellow]")
        return

    table = Table(title="Pending Sandbox Execution Proposal")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Proposal ID", proposal.proposal_id)
    table.add_row("Backend", proposal.backend)
    table.add_row("Command", " ".join(proposal.command))
    table.add_row("Purpose", proposal.purpose)
    table.add_row("CWD", proposal.cwd)
    table.add_row("Network", "[green]enabled[/green]" if proposal.network_enabled else "[red]disabled[/red]")
    table.add_row("Readonly FS", "[green]yes[/green]" if proposal.readonly_filesystem else "[yellow]no[/yellow]")
    table.add_row("Env Keys", ", ".join(proposal.env_keys) if proposal.env_keys else "(none)")
    table.add_row("Preview Kind", proposal.preview_kind)
    table.add_row("Status", proposal.status)
    table.add_row("Created", proposal.created_at)
    console.print(table)


@sandbox_app.command("discard")
def sandbox_discard() -> None:
    """Discard the pending sandbox execution proposal."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)

    if not gate.pending_path.exists():
        console.print("[yellow]No pending sandbox execution proposal to discard.[/yellow]")
        return

    gate.discard()
    console.print("[green]Pending sandbox execution proposal discarded.[/green]")


@sandbox_app.command("execute")
def sandbox_execute() -> None:
    """Execute the pending sandbox proposal when all checks pass.

    v1.8.0: Only the Noop backend supports execution (local policy-gated).
    macOS/Linux/Docker backends remain dry-run only.
    """
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)
    result = gate.execute_pending()

    if result.executed:
        exit_color = "green" if result.exit_code == 0 else "red"
        console.print(
            Panel.fit(
                f"Proposal ID: {result.proposal_id}\n"
                f"Backend: {result.backend}\n"
                f"Executed: [bold green]yes[/bold green]\n"
                f"Dry Run: [bold]false[/bold]\n"
                f"Exit Code: [{exit_color}]{result.exit_code}[/{exit_color}]",
                title="Sandbox Execution Result",
            )
        )
        if result.stdout:
            console.print(Panel(result.stdout.rstrip(), title="stdout", border_style="dim"))
        if result.stderr:
            console.print(Panel(result.stderr.rstrip(), title="stderr", border_style="dim"))
    else:
        console.print(
            Panel.fit(
                f"Proposal ID: {result.proposal_id}\n"
                f"Backend: {result.backend}\n"
                f"Executed: [bold red]no[/bold red]\n"
                f"Dry Run: [bold yellow]true[/bold yellow]\n\n"
                f"[red]{result.message}[/red]",
                title="Sandbox Execution Blocked",
            )
        )


@sandbox_app.command("approve")
def sandbox_approve(
    ttl_minutes: int = typer.Option(30, "--ttl-minutes", min=1, help="Approval TTL in minutes."),
) -> None:
    """Approve the pending sandbox execution proposal. Does NOT execute."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)
    approval = gate.approve(ttl_minutes=ttl_minutes)

    if approval is None:
        console.print("[yellow]No pending sandbox execution proposal to approve.[/yellow]")
        console.print("[yellow]Run 'sac sandbox propose' first.[/yellow]")
        return

    approval_store = SandboxExecutionApprovalStore(project_root)
    console.print(
        Panel.fit(
            f"Proposal ID: {approval.proposal_id}\n"
            f"Backend: {approval.backend}\n"
            f"Approved By: {approval.approved_by}\n"
            f"Approved At: {approval.approved_at[:19]}\n"
            f"Expires At: {approval.expires_at[:19]}\n"
            f"Policy: {approval.policy_version}\n\n"
            f"Approval path: {approval_store.approval_path_for(approval.proposal_id)}",
            title="Sandbox Execution Approved",
        )
    )
    console.print("[yellow]This approval does NOT enable execution in v1.7.6.[/yellow]")


@sandbox_app.command("approvals")
def sandbox_approvals() -> None:
    """Show approval status for the pending sandbox execution proposal."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)
    proposal = gate.load_pending()

    if proposal is None:
        console.print("[yellow]No pending sandbox execution proposal.[/yellow]")
        return

    approval_store = SandboxExecutionApprovalStore(project_root)
    approval = approval_store.load_approval(proposal.proposal_id)
    approved = approval_store.is_approved(
        proposal_id=proposal.proposal_id,
        backend=proposal.backend,
        command_hash=proposal.command_hash,
        preview_hash=proposal.preview_hash,
    )

    table = Table(title="Sandbox Execution Approval Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Proposal ID", proposal.proposal_id)
    table.add_row("Backend", proposal.backend)
    table.add_row("Command", " ".join(proposal.command))
    table.add_row("Approved", "[green]yes[/green]" if approved else "[red]no[/red]")
    if approval:
        table.add_row("Approved By", approval.approved_by)
        table.add_row("Approved At", approval.approved_at[:19])
        table.add_row("Expires At", approval.expires_at[:19])
        table.add_row("Policy", approval.policy_version)
    console.print(table)


@sandbox_app.command("revoke")
def sandbox_revoke() -> None:
    """Revoke approval for the pending sandbox execution proposal."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)
    approval = gate.revoke()

    if approval:
        console.print(f"[green]Approval revoked for proposal {approval.proposal_id}.[/green]")
    else:
        console.print("[yellow]No approval to revoke for current pending proposal.[/yellow]")


@sandbox_app.command("preflight")
def sandbox_preflight() -> None:
    """Run sandbox execution preflight checks. Does NOT execute."""
    project_root = Path.cwd()
    result = SandboxExecutionPreflight(project_root).run()

    table = Table(title="Sandbox Execution Preflight")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Proposal ID", result.proposal_id or "[red]none[/red]")
    table.add_row("Backend", result.backend)
    table.add_row("Command Head", result.command_head or "(none)")
    table.add_row("Approval Valid", "[green]yes[/green]" if result.approval_valid else "[red]no[/red]")
    table.add_row("Command Policy", "[green]ok[/green]" if result.command_policy_ok else "[red]blocked[/red]")
    table.add_row("Network Policy", "[green]ok[/green]" if result.network_policy_ok else "[red]conflict[/red]")
    table.add_row("Backend Available", "[green]yes[/green]" if result.backend_available else "[red]no[/red]")
    table.add_row("Supports Execution", "[green]yes[/green]" if result.backend_supports_execution else "[red]no[/red]")
    table.add_row("Proposal Integrity", "[green]ok[/green]" if result.proposal_integrity_ok else "[red]mismatch[/red]")
    table.add_row("Preview Hash", "[green]ok[/green]" if result.preview_hash_ok else "[red]mismatch[/red]")
    table.add_row("Filesystem Boundary", "[green]ok[/green]" if result.filesystem_boundary_ok else "[red]escape[/red]")
    table.add_row("Final Allowed", "[bold green]YES[/bold green]" if result.allowed else "[bold red]NO[/bold red]")
    console.print(table)

    if result.reasons:
        reason_lines = [f"- {r}" for r in result.reasons]
        console.print(Panel("\n".join(reason_lines), title="[yellow]Reasons[/yellow]"))

    if result.warnings:
        warn_lines = [f"- {w}" for w in result.warnings]
        console.print(Panel("\n".join(warn_lines), title="[dim]Warnings[/dim]"))

    console.print("[yellow]No command was executed.[/yellow]")


executions_app = typer.Typer(help="List and manage sandbox execution result records.")


@executions_app.callback(invoke_without_command=True)
def sandbox_executions(
    status: str = typer.Option("", "--status", help="Filter by status: completed, blocked_claim."),
    backend: str = typer.Option("", "--backend", help="Filter by backend: none, macos_seatbelt, linux_bubblewrap, docker."),
    proposal_id: str = typer.Option("", "--proposal-id", help="Filter by proposal ID (substring match)."),
    limit: int = typer.Option(0, "--limit", min=0, help="Max records to show."),
    sort: str = typer.Option("newest", "--sort", help="Sort order: newest (default) or oldest."),
) -> None:
    """List all sandbox execution result records.

    Use --status, --backend, and --proposal-id to filter results.
    Use --limit N to cap output and --sort newest|oldest to change order.
    """
    project_root = Path.cwd()
    store = SandboxExecutionResultStore(project_root)
    try:
        records = store.filter_by(
            backend=backend if backend else None,
            status=status if status else None,
            proposal_id_substr=proposal_id if proposal_id else None,
            sort_order=sort,
            limit=limit if limit > 0 else None,
        )
    except ValueError as exc:
        console.print(f"[red]Invalid parameter:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not records:
        console.print("[yellow]No sandbox execution result records found.[/yellow]")
        if status or backend or proposal_id:
            console.print("[dim]Try removing filters to see all records.[/dim]")
        return

    table = Table(title="Sandbox Execution Results")
    table.add_column("Attempted At")
    table.add_column("Proposal ID")
    table.add_column("Status")
    table.add_column("Exit Code")
    table.add_column("Command")
    table.add_column("Message")

    for r in records:
        status_color = "green" if r.status == "completed" else "red"
        exit_str = str(r.exit_code) if r.exit_code is not None else "-"
        table.add_row(
            r.attempted_at[:19],
            r.proposal_id[:12] + "...",
            f"[{status_color}]{r.status}[/{status_color}]",
            exit_str,
            r.command_head,
            r.message[:80] if r.message else "",
        )
    console.print(table)


@executions_app.command("stats")
def sandbox_executions_stats() -> None:
    """Show aggregate statistics for sandbox execution results."""
    project_root = Path.cwd()
    store = SandboxExecutionResultStore(project_root)
    st = store.stats()

    table = Table(title="Sandbox Execution Result Statistics")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Total Records", str(st.total_records))
    table.add_row("Completed", str(st.completed_count))
    table.add_row("Blocked Claims", str(st.blocked_claim_count))
    table.add_row("Oldest Attempt", st.oldest_attempted_at or "(none)")
    table.add_row("Newest Attempt", st.newest_attempted_at or "(none)")
    table.add_row("Total Disk (bytes)", str(st.total_bytes))
    console.print(table)


@executions_app.command("prune")
def sandbox_executions_prune(
    keep_latest: int = typer.Option(..., "--keep-latest", min=0, help="Keep the newest N records."),
    status: str = typer.Option("", "--status", help="Only prune records with this status: completed, blocked_claim."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion."),
) -> None:
    """Prune old sandbox execution result records.

    Requires --dry-run (preview only) or --yes (confirm deletion).
    Use --status to limit pruning to a specific record status.
    """
    project_root = Path.cwd()
    store = SandboxExecutionResultStore(project_root)

    if not dry_run and not yes:
        console.print("[red]Prune requires --dry-run or --yes.[/red]")
        raise typer.Exit(code=1)

    status_filter = status if status else None
    try:
        candidates = store.plan_prune(keep_latest=keep_latest, status=status_filter)
    except ValueError as exc:
        console.print(f"[red]Invalid parameter:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    all_records = store.list_all()
    remaining = len(all_records) - len(candidates)

    if dry_run:
        console.print(
            Panel.fit(
                f"Keep latest: {keep_latest}\n"
                f"Status filter: {status_filter or 'all'}\n"
                f"Candidates to delete: {len(candidates)}\n"
                f"Records kept: {remaining}",
                title="Prune Dry Run",
            )
        )
        if candidates:
            cand_table = Table(title="Candidates for Deletion")
            cand_table.add_column("Attempted At")
            cand_table.add_column("Proposal ID")
            cand_table.add_column("Status")
            for r in candidates:
                cand_table.add_row(
                    r.attempted_at[:19],
                    r.proposal_id[:12] + "...",
                    r.status,
                )
            console.print(cand_table)
        return

    # --yes confirmed
    deleted = store.prune(keep_latest=keep_latest, status=status_filter)
    remaining_after = len(store.list_all())
    AuditLogger(project_root).write(
        AuditEvent(
            type="sandbox_execution_results_pruned",
            timestamp=utc_now_iso(),
            status="success",
            message=f"Pruned {deleted} sandbox execution result record(s).",
            metadata={
                "keep_latest": str(keep_latest),
                "status_filter": status_filter or "all",
                "candidate_count": str(len(candidates)),
                "deleted_count": str(deleted),
                "remaining_count": str(remaining_after),
                "proposal_ids": ",".join(r.proposal_id for r in candidates[:20]),
                "proposal_ids_truncated": "true" if len(candidates) > 20 else "false",
            },
        )
    )
    console.print(f"[green]Pruned {deleted} record(s).[/green] {remaining_after} record(s) kept.")


sandbox_app.add_typer(executions_app, name="executions")


@sandbox_app.command("last-execution")
def sandbox_last_execution() -> None:
    """Show the most recent sandbox execution result record."""
    project_root = Path.cwd()
    store = SandboxExecutionResultStore(project_root)
    record = store.latest()

    if record is None:
        console.print("[yellow]No sandbox execution result records found.[/yellow]")
        return

    status_color = "green" if record.status == "completed" else "red"
    exit_color = "green" if record.exit_code == 0 else "red"

    meta_table = Table(title="Last Sandbox Execution Result")
    meta_table.add_column("Field")
    meta_table.add_column("Value")
    meta_table.add_row("Proposal ID", record.proposal_id)
    meta_table.add_row("Attempted At", record.attempted_at)
    meta_table.add_row("Backend", record.backend)
    meta_table.add_row("Executed", "[green]yes[/green]" if record.executed else "[red]no[/red]")
    meta_table.add_row("Exit Code", f"[{exit_color}]{record.exit_code}[/{exit_color}]")
    meta_table.add_row("Duration (ms)", str(record.duration_ms))
    meta_table.add_row("Status", f"[{status_color}]{record.status}[/{status_color}]")
    meta_table.add_row("Command Head", record.command_head)
    meta_table.add_row("Command Hash Prefix", record.command_hash_prefix)
    meta_table.add_row("Message", record.message)
    meta_table.add_row("Stdout Length", str(record.stdout_length))
    meta_table.add_row("Stderr Length", str(record.stderr_length))
    console.print(meta_table)

    if record.stdout_preview:
        console.print(Panel(record.stdout_preview.rstrip(), title="stdout preview", border_style="dim"))
    if record.stderr_preview:
        console.print(Panel(record.stderr_preview.rstrip(), title="stderr preview", border_style="dim"))


@sandbox_app.command("execution")
def sandbox_execution_show(
    show: str = typer.Argument(..., help="Proposal ID of the execution record to show."),
) -> None:
    """Show a single sandbox execution result record by proposal ID."""
    project_root = Path.cwd()
    store = SandboxExecutionResultStore(project_root)
    record = store.load(show)

    if record is None:
        console.print(f"[red]No execution result record found for proposal ID:[/red] {show}")
        raise typer.Exit(code=1)

    status_color = "green" if record.status == "completed" else "red"
    exit_color = "green" if record.exit_code == 0 else "red"

    meta_table = Table(title=f"Sandbox Execution Detail: {record.proposal_id}")
    meta_table.add_column("Field")
    meta_table.add_column("Value")
    meta_table.add_row("Proposal ID", record.proposal_id)
    meta_table.add_row("Attempted At", record.attempted_at)
    meta_table.add_row("Backend", record.backend)
    meta_table.add_row("Executed", "[green]yes[/green]" if record.executed else "[red]no[/red]")
    meta_table.add_row("Exit Code", f"[{exit_color}]{record.exit_code}[/{exit_color}]")
    meta_table.add_row("Duration (ms)", str(record.duration_ms))
    meta_table.add_row("Status", f"[{status_color}]{record.status}[/{status_color}]")
    meta_table.add_row("Command Head", record.command_head)
    meta_table.add_row("Command Hash Prefix", record.command_hash_prefix)
    meta_table.add_row("Message", record.message)
    meta_table.add_row("Stdout Length", str(record.stdout_length))
    meta_table.add_row("Stderr Length", str(record.stderr_length))
    console.print(meta_table)

    if record.stdout_preview:
        console.print(Panel(record.stdout_preview.rstrip(), title="stdout preview", border_style="dim"))
    if record.stderr_preview:
        console.print(Panel(record.stderr_preview.rstrip(), title="stderr preview", border_style="dim"))


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
    level: Optional[str] = typer.Option(None, "--level"),
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


@audit_app.command("verify")
def audit_verify() -> None:
    """Verify audit log hash-chain integrity."""
    ok, message = AuditLogger(Path.cwd()).verify_integrity()
    color = "green" if ok else "red"
    console.print(f"[{color}]{message}[/{color}]")
    if not ok:
        raise typer.Exit(code=1)


@hooks_app.command("approve")
def hooks_approve(
    command: str,
    hook: str = typer.Option("after_apply", "--hook"),
    ttl_hours: int = typer.Option(24, "--ttl-hours", min=1),
) -> None:
    """Approve one exact hook command."""
    approval = HookApprovalStore(Path.cwd()).approve(hook, command, ttl_hours=ttl_hours)
    console.print(f"[green]Hook approved:[/green] {approval.command_hash}")
    console.print(f"Expires: {approval.expires_at}")


@hooks_app.command("list")
def hooks_list() -> None:
    """List stored hook approvals."""
    approvals = HookApprovalStore(Path.cwd()).list()
    table = Table(title="SafeCode Hook Approvals")
    table.add_column("Hook")
    table.add_column("Command")
    table.add_column("Approved At")
    table.add_column("Expires At")
    table.add_column("Hash")
    for approval in approvals:
        table.add_row(approval.hook_name, approval.command, approval.approved_at, approval.expires_at, approval.command_hash[:12])
    console.print(table if approvals else "[yellow]No hook approvals found.[/yellow]")


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
app.add_typer(audit_app, name="audit")
app.add_typer(hooks_app, name="hooks")
app.add_typer(sandbox_app, name="sandbox")


def main() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    main()
