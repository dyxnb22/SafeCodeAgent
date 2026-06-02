"""Sandbox proposal, approval, and preflight commands (v2.8.6 module split)."""

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from safecode.agent.approvals import HumanCheckpointPresenter
from safecode.cli_shared import console, show_human_checkpoint
from safecode.config import SafeCodeConfig
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.execution import SandboxExecutionGate
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.preflight import SandboxExecutionPreflight
from safecode.tools.gate import ToolCallGate


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


def sandbox_discard() -> None:
    """Discard the pending sandbox execution proposal."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)

    if not gate.pending_path.exists():
        console.print("[yellow]No pending sandbox execution proposal to discard.[/yellow]")
        return

    gate.discard()
    console.print("[green]Pending sandbox execution proposal discarded.[/green]")


def sandbox_execute() -> None:
    """Execute the pending sandbox proposal when all checks pass.

    v1.8.0: Only the Noop backend supports execution (local policy-gated).
    macOS/Linux/Docker backends remain dry-run only.
    """
    project_root = Path.cwd()
    # Universal gate: sandbox.execute is high-risk; consult before side effects.
    tool_gate_result = ToolCallGate().check_intent("sandbox.execute", approved=True)
    if not tool_gate_result.allowed:
        console.print(f"[red]Blocked by tool gate:[/red] {tool_gate_result.reason}")
        raise typer.Exit(code=1)
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
    console.print("[yellow]Run 'sac sandbox execute' to execute the approved proposal.[/yellow]")


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


def sandbox_revoke() -> None:
    """Revoke approval for the pending sandbox execution proposal."""
    project_root = Path.cwd()
    gate = SandboxExecutionGate(project_root)
    approval = gate.revoke()

    if approval:
        console.print(f"[green]Approval revoked for proposal {approval.proposal_id}.[/green]")
    else:
        console.print("[yellow]No approval to revoke for current pending proposal.[/yellow]")


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
