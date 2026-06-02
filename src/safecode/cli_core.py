import os
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint
from safecode.cli_shared_json import CLIJSONResponse, render_json

from safecode.agent.approvals import HumanCheckpointPresenter
from safecode.agent.orchestrator import AgentOrchestrator
from safecode.audit.models import AuditEvent
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError
from safecode.shell.risk import RiskLevel
from safecode.shell.runner import ShellRunner
from safecode.tools.gate import GateError, ToolCallGate
from safecode.utils.time import utc_now_iso

core_app = typer.Typer()


@core_app.command()
def ask(
    question: str,
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Ask a read-only question about the current project."""
    project_root = Path.cwd()
    try:
        answer = AgentOrchestrator(project_root).ask(question)
    except Exception as exc:
        log_cli_error("cli.ask", "ask command failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="ask", status="error", error=str(exc))))
        else:
            console.print(f"[red]Ask failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if json_output:
        print(render_json(CLIJSONResponse(command="ask", status="success", data={"answer": str(answer.content)})))
        return
    console.print(answer)


@core_app.command()
def edit(
    task: str,
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    retry_from_last_failure: bool = typer.Option(False, "--retry-from-last-failure", help="Prepend last failure context from the journal."),
) -> None:
    """Create a pending patch proposal without modifying files."""
    project_root = Path.cwd()
    # Gate: patch.propose is write-class; the user invoking sac edit is the approval gesture.
    gate_result = ToolCallGate().check_intent("patch.propose", approved=True)
    if not gate_result.allowed:
        if json_output:
            print(render_json(CLIJSONResponse(command="edit", status="error", error=gate_result.reason)))
        else:
            console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
        raise typer.Exit(code=1)

    effective_task = task
    if retry_from_last_failure:
        effective_task = _inject_last_failure_context(project_root, task)

    try:
        result = AgentOrchestrator(project_root).edit(effective_task)
    except (PatchParseError, PatchValidationError) as exc:
        log_cli_error("cli.edit", "patch proposal failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="edit", status="error", error=str(exc))))
        else:
            console.print(f"[red]Patch proposal failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.edit", "edit command failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="edit", status="error", error=str(exc))))
        else:
            console.print(f"[red]Edit failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        print(render_json(CLIJSONResponse(
            command="edit",
            status="success",
            data={
                "pending_patch_path": str(result.pending_patch_path),
                "diff_text": result.diff_text,
            },
        )))
        return
    console.print(Panel.fit(f"Pending patch saved: {result.pending_patch_path}", title="SafeCode"))
    console.print(Syntax(result.diff_text, "diff", theme="ansi_dark"))
    if result.scope_result and result.scope_result.warning:
        console.print(f"[yellow]{result.scope_result.warning}[/yellow]")


@core_app.command()
def apply(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Apply the latest pending patch after review."""
    project_root = Path.cwd()
    orchestrator = AgentOrchestrator(project_root)

    try:
        preview = orchestrator.preview_apply()
    except (FileNotFoundError, PatchValidationError) as exc:
        log_cli_error("cli.apply", "apply preview failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=str(exc))))
        else:
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
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="cancelled", data={"patch_id": preview.proposal.id})))
        else:
            console.print("[yellow]Patch was not applied.[/yellow]")
        raise typer.Exit(code=0)

    # Gate: human confirmed above — validate the apply tool call before side effects.
    gate_result = ToolCallGate().check(
        "patch.apply", {"patch_id": preview.proposal.id}, approved=True
    )
    if not gate_result.allowed:
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=gate_result.reason)))
        else:
            console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
        raise typer.Exit(code=1)

    try:
        result = orchestrator.apply(preview.proposal)
    except PatchValidationError as exc:
        log_cli_error("cli.apply", "apply command failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=str(exc))))
        else:
            console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.apply", "apply command failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=str(exc))))
        else:
            console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        print(render_json(CLIJSONResponse(
            command="apply",
            status="success",
            data={
                "patch_id": result.proposal.id,
                "checkpoint_id": result.checkpoint.checkpoint_id,
                "files": list(result.files),
            },
        )))
        return
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
    # Gate: --last is the explicit approval gesture for this write-class operation.
    gate_result = ToolCallGate().check_intent("checkpoint.rollback", approved=True)
    if not gate_result.allowed:
        console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
        raise typer.Exit(code=1)

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
def run_command(
    command: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve medium/high risk commands."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Run a shell command through SafeCode risk checks."""
    project_root = Path.cwd()
    runner = ShellRunner(project_root)
    risk = runner.assess(command)
    if not json_output:
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
        if not json_output:
            show_human_checkpoint(checkpoint)
        approved = typer.confirm(checkpoint.prompt, default=False)
    if risk.level == RiskLevel.HIGH and not yes:
        if not json_output:
            console.print("[red]High-risk command blocked by policy.[/red]")
        approved = False
    elif risk.level == RiskLevel.HIGH and yes:
        if not json_output:
            console.print("[red]High-risk command remains blocked even with --yes.[/red]")

    # Gate: only call when the command will actually execute (approved is True).
    # For unapproved/blocked commands the existing risk logic handles the outcome.
    if approved:
        gate_result = ToolCallGate().check(
            "shell.run", {"command": command, "approved": True}, approved=True
        )
        if not gate_result.allowed:
            if json_output:
                print(render_json(CLIJSONResponse(command="run", status="error", error=gate_result.reason)))
            else:
                console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
            raise typer.Exit(code=1)

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

    if json_output:
        status = "success" if result.executed and result.exit_code == 0 else "error"
        print(render_json(CLIJSONResponse(
            command="run",
            status=status,
            data={
                "executed": result.executed,
                "exit_code": result.exit_code,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "risk": str(result.risk.level),
            },
        )))
    else:
        if result.stdout:
            console.print(result.stdout)
        if result.stderr:
            console.print(f"[red]{result.stderr}[/red]")

    # Honest exit codes: 125=approval required, 126=policy blocked.
    # Set SAFECODE_RUN_LEGACY_EXIT_CODE=1 for one migration cycle to get exit code 1 instead.
    if not result.executed and os.environ.get("SAFECODE_RUN_LEGACY_EXIT_CODE") == "1":
        raise typer.Exit(code=1)
    raise typer.Exit(code=result.exit_code)


def _inject_last_failure_context(project_root: Path, task: str) -> str:
    """Prepend last failure context from the journal to the task string."""
    from safecode.agent.session import AgentSessionStore
    from safecode.context.redactor import redact_secrets
    from safecode.state.journal import AgentJournalStore

    store = AgentSessionStore(project_root)
    journal = AgentJournalStore(project_root)
    state = store.load()
    if state is None:
        console.print("[yellow]No agent session found; proceeding without failure context.[/yellow]")
        return task

    failure_ctx = journal.get_last_failure_context(state.session_id)
    if failure_ctx is None:
        console.print("[yellow]No failure context found in journal; proceeding normally.[/yellow]")
        return task

    redacted = redact_secrets(failure_ctx)
    return f"[Previous failure context]\n{redacted}\n\n[Task]\n{task}"

