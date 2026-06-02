"""Sandbox execution result commands (v2.8.6 module split)."""

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.cli_shared import console
from safecode.sandbox.execution import SandboxExecutionResultStore
from safecode.utils.time import utc_now_iso

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
