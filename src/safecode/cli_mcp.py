from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint

import json

from safecode.agent.approvals import HumanCheckpointPresenter
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.mcp.discovery import MCPDiscovery
from safecode.mcp.proposal import MCPWriteProposalStore
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.utils.time import utc_now_iso

mcp_app = typer.Typer(
    help=(
        "Inspect configured MCP servers and tools.\n\n"
        "[dim]Current MCP support is a subprocess JSON shim: configured commands receive "
        "JSON on stdin and return JSON on stdout. This is not a full MCP JSON-RPC client "
        "(no live tools/list or tools/call protocol).[/dim]"
    )
)


@mcp_app.command("tools")
def mcp_tools() -> None:
    """List configured MCP tools.

    Tools are read from .sac/mcp.toml config, not from a live JSON-RPC tools/list call.
    Current MCP support is a subprocess JSON shim.
    """
    tools = MCPDiscovery(Path.cwd()).list_tools()
    table = Table(title="MCP Tools")
    table.add_column("Server")
    table.add_column("Tool")
    table.add_column("Risk")
    for tool in tools:
        table.add_row(tool.server, tool.name, tool.risk)
    console.print(table if tools else "[yellow]No MCP tools configured.[/yellow]")
    console.print(
        "[dim]MCP support is a subprocess JSON shim. "
        "Tools are read from config, not from a live MCP JSON-RPC tools/list call.[/dim]"
    )


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
        log_cli_error("cli.mcp.call_readonly", "invalid MCP input JSON", exc)
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
        log_cli_error("cli.mcp.propose_write", "invalid MCP input JSON", exc)
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
    checkpoint = HumanCheckpointPresenter(project_root).checkpoint(
        checkpoint_type="mcp_write",
        title="MCP Write Checkpoint",
        prompt="Review this MCP write proposal before applying it.",
        risk_level=proposal.risk_level,
        summary=f"MCP write proposal for {proposal.server}.{proposal.tool}; no tool was executed.",
        subject=proposal.proposal_id,
        metadata={
            "proposal_id": proposal.proposal_id,
            "server": proposal.server,
            "tool": proposal.tool,
            "classification": proposal.classification,
        },
    )
    show_human_checkpoint(checkpoint)
    console.print("[yellow]Review and apply through the MCP proposal flow; no write was executed.[/yellow]")


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


