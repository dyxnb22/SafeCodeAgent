"""Sandbox status and plan commands (v2.8.6 module split)."""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode import __version__
from safecode.cli_shared import console
from safecode.config import SafeCodeConfig
from safecode.sandbox.capabilities import SandboxBackend
from safecode.sandbox.execution import SandboxExecutionResultStore
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.planner import SandboxPlanner


def sandbox_status() -> None:
    """Show available sandbox backends and recommendations."""
    project_root = Path.cwd()
    plan = SandboxPlanner(project_root).plan()

    console.print(
        Panel.fit(
            "[bold]SafeCode Sandbox Execution Scope[/bold]\n"
            "Noop backend: [yellow]policy-gated[/yellow] (no OS containment; ShellRunner policy + approval only)\n"
            "Docker backend: [green]executing[/green] (preview — requires running daemon)\n"
            "macOS Seatbelt: [green]executing[/green] (preview — requires sandbox-exec on PATH)\n"
            "Linux Bubblewrap: [green]executing[/green] (preview — requires bwrap on PATH)",
            title=f"[green]Execution Scope ({__version__})[/green]",
        )
    )

    cap_table = Table(title="Sandbox Backend Status")
    cap_table.add_column("Backend")
    cap_table.add_column("Available")
    cap_table.add_column("Mode")
    cap_table.add_column("Platforms")
    cap_table.add_column("Recommended For")
    for cap in plan.capabilities:
        if cap.backend == SandboxBackend.NONE:
            mode = "[yellow]policy-gated[/yellow] (no OS containment)"
        elif cap.backend == SandboxBackend.DOCKER:
            mode = "[green]executing[/green] (preview)"
        elif cap.backend == SandboxBackend.MACOS_SEATBELT:
            mode = "[green]executing[/green] (preview)"
        elif cap.backend == SandboxBackend.LINUX_BUBBLEWRAP:
            mode = "[green]executing[/green] (preview)"
        else:
            mode = "[yellow]plan-only[/yellow]"
        cap_table.add_row(
            cap.backend.value,
            "[green]yes[/green]" if cap.available else "[red]no[/red]",
            mode,
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

    if exec_plan.backend == SandboxBackend.NONE:
        backend_mode = "[yellow]policy-gated[/yellow] (Noop — no OS containment)"
    elif exec_plan.backend == SandboxBackend.DOCKER:
        backend_mode = "[green]executing[/green] (Docker preview — requires approval and daemon)"
    elif exec_plan.backend == SandboxBackend.MACOS_SEATBELT:
        backend_mode = "[green]executing[/green] (macOS Seatbelt preview — requires approval and sandbox-exec)"
    elif exec_plan.backend == SandboxBackend.LINUX_BUBBLEWRAP:
        backend_mode = "[green]executing[/green] (Linux Bubblewrap preview — requires approval and bwrap)"
    else:
        backend_mode = "[bold yellow]plan-only / dry-run[/bold yellow] (no OS-level execution)"

    table = Table(title="Sandbox Execution Plan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Backend", exec_plan.backend.value)
    table.add_row("Backend Mode", backend_mode)
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

    _EXECUTING_BACKENDS = {
        SandboxBackend.DOCKER,
        SandboxBackend.MACOS_SEATBELT,
        SandboxBackend.LINUX_BUBBLEWRAP,
    }
    if exec_plan.backend in _EXECUTING_BACKENDS:
        _backend_labels = {
            SandboxBackend.DOCKER: "Docker container (daemon must be running)",
            SandboxBackend.MACOS_SEATBELT: "macOS sandbox-exec (sandbox-exec must be on PATH)",
            SandboxBackend.LINUX_BUBBLEWRAP: "Linux bwrap (bwrap must be on PATH)",
        }
        backend_label = _backend_labels[exec_plan.backend]
        console.print(
            Panel.fit(
                "[bold yellow]This command was NOT executed.[/bold yellow]\n"
                "Use 'sac sandbox propose' → 'sac sandbox approve' → 'sac sandbox execute'\n"
                f"to run the command via {backend_label}.",
                title="Dry Run",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold yellow]This command was NOT executed.[/bold yellow]\n"
                "Noop execution is policy-gated only; it does not add OS containment.",
                title="Dry Run",
            )
        )
