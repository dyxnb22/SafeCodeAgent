from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint

from safecode.audit.logger import AuditLogger
from safecode.doctor import Doctor
from safecode.eval.cases import default_cases
from safecode.eval.runner import EvalRunner
from safecode.export.bundle import Exporter
from safecode.hooks.approvals import HookApprovalStore
from safecode.ide.bridge import pending_diff_target, selected_file_targets
from safecode.ide.manifest import render_manifest, write_manifest
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.store import MemoryStore
from safecode.project.rules import ProjectRules
from safecode.queue.store import QueueStore
from safecode.release.checklist import render_release_checklist
from safecode.report.render import ReportRenderer

ops_app = typer.Typer()
queue_app = typer.Typer(help="Manage a tiny local task queue.")
export_app = typer.Typer(help="Export SafeCode reports.")
ide_app = typer.Typer(help="Generate IDE adapter metadata.")
release_app = typer.Typer(help="Generate release helpers.")
logs_app = typer.Typer(help="Inspect runtime logs.")
audit_app = typer.Typer(help="Inspect and verify audit logs.")
hooks_app = typer.Typer(help="Approve and inspect project hooks.")


@ops_app.command("rules")
def rules(init: bool = typer.Option(False, "--init")) -> None:
    """Show or initialize SAC.md project rules."""
    rules_store = ProjectRules(Path.cwd())
    if init:
        rules_store.ensure()
    console.print(rules_store.read() or "[yellow]No SAC.md found. Run sac rules --init.[/yellow]")


@ops_app.command("memory")
def memory_set(key: str, value: str) -> None:
    """Remember a low-risk project fact."""
    MemoryStore(Path.cwd()).remember(key, value)
    console.print("[green]Memory updated.[/green]")


@ops_app.command("report")
def report() -> None:
    """Render a Markdown report from recent audit events."""
    console.print(ReportRenderer(Path.cwd()).render_markdown())


@export_app.command("report")
def export_report(output: Path = typer.Option(Path(".sac/reports/latest.md"), "--output", "-o")) -> None:
    """Export a Markdown report to a file."""
    path = Exporter(Path.cwd()).report(output)
    console.print(f"Report exported: {path}")


@ops_app.command("eval")
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


@ide_app.command("open-diff")
def ide_open_diff() -> None:
    """Print the materialized pending diff target for an IDE bridge."""
    try:
        target = pending_diff_target(Path.cwd())
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"{target.uri}\n{target.path}")


@ide_app.command("open-files")
def ide_open_files(query: str, limit: int = typer.Option(5, "--limit", min=1)) -> None:
    """Print selected safe file targets for an IDE bridge."""
    targets = selected_file_targets(Path.cwd(), query, limit=limit)
    if not targets:
        console.print("[yellow]No selected files found.[/yellow]")
        return
    table = Table(title="IDE Open Targets")
    table.add_column("Label")
    table.add_column("URI")
    table.add_column("Path")
    for target in targets:
        table.add_row(target.label, target.uri, str(target.path))
    console.print(table)
    for target in targets:
        console.print(f"{target.uri}\n{target.path}")


@release_app.command("checklist")
def release_checklist(version: str) -> None:
    """Render a release checklist."""
    console.print(render_release_checklist(version))


@ops_app.command("doctor")
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
