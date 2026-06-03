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
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.mcp.config import MCPConfigStore, MCPServerConfig, StdioArgvError, resolve_stdio_argv
from safecode.mcp.discovery import MCPDiscovery, discover_stdio_tools
from safecode.mcp.lifecycle import MCPLifecycleManager
from safecode.mcp.proposal import MCPWriteProposalStore
from safecode.mcp.runner import MCPReadOnlyRunner
from safecode.tools.gate import ToolCallGate
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
    # Gate: mcp.call_readonly is low-risk and does not require explicit approval.
    gate_result = ToolCallGate().check(
        "mcp.call_readonly",
        {"tool_name": f"{server}.{tool}", "input_json": payload},
        approved=False,
    )
    if not gate_result.allowed:
        console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
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

    # Gate: mcp.propose_write is write-class; user invoking sac mcp propose-write is approval.
    gate_result = ToolCallGate().check(
        "mcp.propose_write",
        {"tool_name": f"{server}.{tool}", "input_json": payload},
        approved=True,
    )
    if not gate_result.allowed:
        console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
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


@mcp_app.command("stdio-status")
def mcp_stdio_status(
    server: str,
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show stdio argv status for a configured MCP server. [EXPERIMENTAL]

    Reads server config from .sac/mcp.toml and reports whether stdio argv is
    configured.  No subprocess is launched.  MCP stdio is experimental.
    """
    project_root = Path.cwd()
    servers = MCPConfigStore(project_root).list_servers()
    server_names = [s.name for s in servers]

    if server not in server_names:
        if json_output:
            print(render_json(CLIJSONResponse(
                command="mcp stdio-status",
                status="error",
                error=f"MCP server not found: '{server}'",
            )))
        else:
            console.print(f"[red]MCP server not found:[/red] '{server}'")
            console.print(f"[dim]Configured servers: {server_names or ['(none)']}[/dim]")
        raise typer.Exit(code=1)

    cfg = next(s for s in servers if s.name == server)
    has_argv = cfg.argv is not None and len(cfg.argv) > 0

    if json_output:
        print(render_json(CLIJSONResponse(
            command="mcp stdio-status",
            status="success",
            data={
                "server": server,
                "stdio_configured": has_argv,
                "enabled": cfg.enabled,
                "experimental": True,
            },
        )))
    else:
        status_label = "[green]configured[/green]" if has_argv else "[yellow]not configured[/yellow]"
        enabled_label = "[green]enabled[/green]" if cfg.enabled else "[red]disabled[/red]"
        console.print(f"[bold]MCP server:[/bold] {server}")
        console.print(f"  Status:          {enabled_label}")
        console.print(f"  Stdio argv:      {status_label}")
        console.print(
            "[dim][EXPERIMENTAL] MCP stdio transport is experimental. "
            "No subprocess was launched.[/dim]"
        )


@mcp_app.command("stdio-discover")
def mcp_stdio_discover(
    server: str,
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    timeout: float = typer.Option(10.0, "--timeout", help="Discovery timeout in seconds."),
) -> None:
    """Discover tools from a stdio MCP server via tools/list. [EXPERIMENTAL]

    Launches the configured stdio subprocess, sends a tools/list request, and
    prints discovered tools.  Only tools/list is called — no tools/call is
    issued.  MCP stdio is experimental.
    """
    project_root = Path.cwd()
    servers = MCPConfigStore(project_root).list_servers()

    try:
        argv = resolve_stdio_argv(servers, server)
    except StdioArgvError as exc:
        if json_output:
            print(render_json(CLIJSONResponse(
                command="mcp stdio-discover",
                status="error",
                error=str(exc),
            )))
        else:
            console.print(f"[red]Cannot resolve stdio argv:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    result = discover_stdio_tools(server, argv, timeout_seconds=timeout)

    if json_output:
        schemas_data = [
            {
                "server": s.server,
                "tool": s.tool,
                "classification": s.classification,
                "description": s.description,
                "args": list(s.args),
            }
            for s in result.schemas
        ]
        status = "success" if result.success else "error"
        response = CLIJSONResponse(
            command="mcp stdio-discover",
            status=status,
            data={
                "server": result.server_name,
                "tools_found": len(result.schemas),
                "skipped": result.skipped_count,
                "tools": schemas_data,
                "experimental": True,
            },
        )
        if not result.success:
            response = CLIJSONResponse(
                command="mcp stdio-discover",
                status="error",
                data={
                    "server": result.server_name,
                    "tools_found": 0,
                    "skipped": result.skipped_count,
                    "tools": [],
                    "experimental": True,
                },
                error=result.error or "discovery failed",
            )
        print(render_json(response))
    else:
        console.print(f"[bold][EXPERIMENTAL][/bold] MCP stdio discover: [cyan]{server}[/cyan]")
        if not result.success:
            console.print(f"[red]Discovery failed:[/red] {result.error or 'unknown error'}")
            if result.skipped_count:
                console.print(f"[dim]Skipped malformed entries: {result.skipped_count}[/dim]")
            raise typer.Exit(code=1)

        if not result.schemas:
            console.print("[yellow]No tools discovered.[/yellow]")
            if result.skipped_count:
                console.print(f"[dim]Skipped malformed entries: {result.skipped_count}[/dim]")
        else:
            table = Table(title=f"Discovered tools — {server} (experimental)")
            table.add_column("Tool")
            table.add_column("Classification")
            table.add_column("Description")
            for schema in result.schemas:
                table.add_row(schema.tool, schema.classification, schema.description or "")
            console.print(table)
            if result.skipped_count:
                console.print(f"[dim]Skipped malformed entries: {result.skipped_count}[/dim]")

        console.print(
            "[dim][EXPERIMENTAL] MCP stdio transport is experimental. "
            "Only tools/list was called — no tools/call was issued.[/dim]"
        )


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


# ── Lifecycle commands (v3.8.0, experimental) ─────────────────────────────────


@mcp_app.command("start")
def mcp_start(
    server: str = typer.Argument(..., help="MCP server name from .sac/mcp.toml"),
) -> None:
    """Start a configured MCP server process in the background. [EXPERIMENTAL]

    Requires the server to have an ``argv`` list in .sac/mcp.toml.
    Tracks PID in .sac/mcp/<server>.pid.  Idempotent if already running.
    Emits an audit event on each attempt.
    """
    project_root = Path.cwd()
    manager = MCPLifecycleManager(project_root)
    result = manager.start(server)
    if result.success:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(code=1)


@mcp_app.command("stop")
def mcp_stop(
    server: str = typer.Argument(..., help="MCP server name from .sac/mcp.toml"),
) -> None:
    """Stop a running MCP server process. [EXPERIMENTAL]

    Idempotent: exits 0 even if the server is not running or the PID is missing.
    Emits an audit event on each attempt.
    """
    project_root = Path.cwd()
    manager = MCPLifecycleManager(project_root)
    result = manager.stop(server)
    # stop always returns success (idempotent); only show in context
    console.print(f"[green]{result.message}[/green]")


@mcp_app.command("restart")
def mcp_restart(
    server: str = typer.Argument(..., help="MCP server name from .sac/mcp.toml"),
) -> None:
    """Stop then start a configured MCP server process. [EXPERIMENTAL]

    Emits audit events for the stop and start transitions.
    """
    project_root = Path.cwd()
    manager = MCPLifecycleManager(project_root)
    result = manager.restart(server)
    if result.success:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(code=1)


# ── Doctor command (v3.8.1, experimental) ──────────────────────────────────────


def _doctor_server_info(
    project_root: Path,
    cfg: MCPServerConfig,
    audit_logger: AuditLogger,
    lifecycle_manager: MCPLifecycleManager,
) -> dict:
    """Collect doctor info for one server. Pure read — never spawns subprocesses."""
    import shutil

    # Binary path: first token of the command string (not argv; matches subprocess shim).
    binary = cfg.command.split()[0] if cfg.command.strip() else ""
    binary_path = shutil.which(binary) if binary else None

    # Last call status from audit log (most recent mcp_call_* or mcp_write_* event for this server).
    mcp_event_types = {
        "mcp_call_proposed", "mcp_call_started", "mcp_call_completed", "mcp_call_blocked",
        "mcp_write_proposed", "mcp_write_blocked", "mcp_approved_write_started",
        "mcp_approved_write_completed",
    }
    last_call_status: str | None = None
    last_call_type: str | None = None
    last_call_ts: str | None = None
    try:
        recent = audit_logger.read_recent(limit=200)
        for event in reversed(recent):
            if event.type in mcp_event_types:
                meta = event.metadata or {}
                if meta.get("server") == cfg.name:
                    last_call_status = event.status
                    last_call_type = event.type
                    last_call_ts = event.timestamp
                    break
    except Exception:
        pass

    # Lifecycle PID.
    pid: int | None = lifecycle_manager.read_pid(cfg.name)
    is_running = lifecycle_manager.is_running(cfg.name)

    return {
        "server": cfg.name,
        "enabled": cfg.enabled,
        "scope": cfg.scope,
        "binary": binary or None,
        "binary_path": binary_path,
        "stdio_configured": cfg.argv is not None and len(cfg.argv) > 0,
        "last_call_type": last_call_type,
        "last_call_status": last_call_status,
        "last_call_timestamp": last_call_ts,
        "lifecycle_pid": pid,
        "lifecycle_running": is_running,
    }


@mcp_app.command("doctor")
def mcp_doctor(
    server: Optional[str] = typer.Argument(None, help="Server name; omit to check all servers."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show diagnostic info for configured MCP servers. [EXPERIMENTAL]

    Reports binary path, scope, last call status from audit log, and lifecycle
    PID.  Pure read — no subprocess is launched.
    """
    project_root = Path.cwd()
    config_store = MCPConfigStore(project_root)
    audit_logger = AuditLogger(project_root)
    lifecycle_manager = MCPLifecycleManager(project_root)

    servers = config_store.list_servers()

    if server is not None:
        servers = [s for s in servers if s.name == server]
        if not servers:
            if json_output:
                print(render_json(CLIJSONResponse(
                    command="mcp doctor",
                    status="error",
                    error=f"MCP server not found: '{server}'",
                )))
            else:
                console.print(f"[red]MCP server not found:[/red] '{server}'")
            raise typer.Exit(code=1)

    if not servers:
        if json_output:
            print(render_json(CLIJSONResponse(command="mcp doctor", status="success", data={"servers": []})))
        else:
            console.print("[yellow]No MCP servers configured.[/yellow]")
        return

    results = [_doctor_server_info(project_root, cfg, audit_logger, lifecycle_manager) for cfg in servers]

    if json_output:
        print(render_json(CLIJSONResponse(
            command="mcp doctor",
            status="success",
            data={"servers": results, "experimental": True},
        )))
        return

    for info in results:
        console.print(f"\n[bold]MCP server:[/bold] {info['server']}")
        enabled_label = "[green]enabled[/green]" if info["enabled"] else "[red]disabled[/red]"
        console.print(f"  Enabled:           {enabled_label}")
        console.print(f"  Scope:             {info['scope']}")
        binary_display = info["binary_path"] or info["binary"] or "[dim](not set)[/dim]"
        console.print(f"  Binary path:       {binary_display}")
        stdio_label = "[green]yes[/green]" if info["stdio_configured"] else "[yellow]no[/yellow]"
        console.print(f"  Stdio configured:  {stdio_label}")
        if info["last_call_type"]:
            console.print(f"  Last call type:    {info['last_call_type']}")
            console.print(f"  Last call status:  {info['last_call_status']}")
            console.print(f"  Last call at:      {info['last_call_timestamp']}")
        else:
            console.print("  Last call:         [dim](no audit record found)[/dim]")
        if info["lifecycle_pid"]:
            running_label = "[green]running[/green]" if info["lifecycle_running"] else "[red]dead (stale PID)[/red]"
            console.print(f"  Lifecycle PID:     {info['lifecycle_pid']} ({running_label})")
        else:
            console.print("  Lifecycle PID:     [dim](not tracked)[/dim]")

    console.print("\n[dim][EXPERIMENTAL] MCP doctor is experimental. No subprocess was launched.[/dim]")
