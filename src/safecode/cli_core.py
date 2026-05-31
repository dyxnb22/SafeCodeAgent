from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint

from safecode.agent.approvals import HumanCheckpointPresenter
from safecode.agent.orchestrator import AgentOrchestrator
from safecode.audit.models import AuditEvent
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError
from safecode.shell.risk import RiskLevel
from safecode.shell.runner import ShellRunner
from safecode.utils.time import utc_now_iso

core_app = typer.Typer()


@core_app.command()
def ask(question: str) -> None:
    """Ask a read-only question about the current project."""
    project_root = Path.cwd()
    try:
        answer = AgentOrchestrator(project_root).ask(question)
    except Exception as exc:
        log_cli_error("cli.ask", "ask command failed", exc)
        console.print(f"[red]Ask failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(answer)


@core_app.command()
def edit(task: str) -> None:
    """Create a pending patch proposal without modifying files."""
    project_root = Path.cwd()
    try:
        result = AgentOrchestrator(project_root).edit(task)
    except (PatchParseError, PatchValidationError) as exc:
        log_cli_error("cli.edit", "patch proposal failed", exc)
        console.print(f"[red]Patch proposal failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.edit", "edit command failed", exc)
        console.print(f"[red]Edit failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(Panel.fit(f"Pending patch saved: {result.pending_patch_path}", title="SafeCode"))
    console.print(Syntax(result.diff_text, "diff", theme="ansi_dark"))
    if result.scope_result and result.scope_result.warning:
        console.print(f"[yellow]{result.scope_result.warning}[/yellow]")


@core_app.command()
def apply() -> None:
    """Apply the latest pending patch after review."""
    project_root = Path.cwd()
    orchestrator = AgentOrchestrator(project_root)

    try:
        preview = orchestrator.preview_apply()
    except (FileNotFoundError, PatchValidationError) as exc:
        log_cli_error("cli.apply", "apply preview failed", exc)
        console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(Syntax(preview.diff_text, "diff", theme="ansi_dark"))
    checkpoint = HumanCheckpointPresenter(project_root).checkpoint(
        checkpoint_type="patch_apply",
        title="Patch Apply Checkpoint",
        prompt="Apply this patch?",
        risk_level="write",
        summary=f"Apply pending patch {preview.proposal.id} touching {len(preview.proposal.blocks)} file operation(s).",
        subject=preview.proposal.id,
        metadata={
            "patch_id": preview.proposal.id,
            "file_count": str(len(preview.proposal.blocks)),
        },
    )
    show_human_checkpoint(checkpoint)
    approved = typer.confirm(checkpoint.prompt, default=False)
    if not approved:
        console.print("[yellow]Patch was not applied.[/yellow]")
        raise typer.Exit(code=0)

    try:
        result = orchestrator.apply(preview.proposal)
    except PatchValidationError as exc:
        log_cli_error("cli.apply", "apply command failed", exc)
        console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.apply", "apply command failed", exc)
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


@core_app.command()
def rollback(last: bool = typer.Option(False, "--last", help="Rollback the latest checkpoint.")) -> None:
    """Rollback a previous applied patch."""
    if not last:
        console.print("[red]Only --last is planned for v0.1.[/red]")
        raise typer.Exit(code=1)

    project_root = Path.cwd()
    try:
        result = AgentOrchestrator(project_root).rollback_last()
    except FileNotFoundError as exc:
        log_cli_error("cli.rollback", "rollback failed", exc)
        console.print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.rollback", "rollback failed", exc)
        console.print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Rolled back checkpoint: {result.checkpoint.checkpoint_id}\n"
            f"Files: {', '.join(result.files)}",
            title="SafeCode",
        )
    )


@core_app.command()
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


@core_app.command("run")
def run_command(command: str, yes: bool = typer.Option(False, "--yes", "-y", help="Approve medium/high risk commands.")) -> None:
    """Run a shell command through SafeCode risk checks."""
    project_root = Path.cwd()
    runner = ShellRunner(project_root)
    risk = runner.assess(command)
    console.print(Panel.fit("\n".join([f"Risk: {risk.level}", *risk.reasons]), title="Shell Risk"))

    approved = yes
    if risk.level == RiskLevel.MEDIUM and not yes:
        checkpoint = HumanCheckpointPresenter(project_root).checkpoint(
            checkpoint_type="shell_run",
            title="Shell Command Checkpoint",
            prompt="Run this medium-risk command?",
            risk_level=str(risk.level),
            summary=f"Run medium-risk shell command with {len(risk.reasons)} risk reason(s).",
            subject=command,
            metadata={
                "command_head": risk.tokens[0] if risk.tokens else "",
                "reason_count": str(len(risk.reasons)),
            },
        )
        show_human_checkpoint(checkpoint)
        approved = typer.confirm(checkpoint.prompt, default=False)
    if risk.level == RiskLevel.HIGH and not yes:
        console.print("[red]High-risk command blocked by policy.[/red]")
        approved = False
    elif risk.level == RiskLevel.HIGH and yes:
        console.print("[red]High-risk command remains blocked even with --yes.[/red]")

    result = runner.run(command, approved=approved)
    runtime_logger().info(
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


