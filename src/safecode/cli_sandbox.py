from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint

from safecode.agent.approvals import HumanCheckpointPresenter
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.execution import SandboxExecutionGate, SandboxExecutionResultStore
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.preflight import SandboxExecutionPreflight
from safecode.sandbox.planner import SandboxPlanner
from safecode.utils.time import utc_now_iso

sandbox_app = typer.Typer(help="Check OS sandbox capabilities and recommendations.")


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
    proposal = gate.load_pending()
    if proposal is not None:
        checkpoint = HumanCheckpointPresenter(project_root).checkpoint(
            checkpoint_type="sandbox_execute",
            title="Sandbox Execution Checkpoint",
            prompt="Approve this sandbox execution proposal?",
            risk_level="execute",
            summary=f"Approve sandbox proposal {proposal.proposal_id} for backend {proposal.backend}.",
            subject=proposal.proposal_id,
            metadata={
                "proposal_id": proposal.proposal_id,
                "backend": proposal.backend,
                "command_head": proposal.command[0] if proposal.command else "",
            },
        )
        show_human_checkpoint(checkpoint)
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


