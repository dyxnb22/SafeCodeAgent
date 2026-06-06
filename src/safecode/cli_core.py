import os
import sys
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
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import grant_ephemeral_trust, revoke_ephemeral_trust
from safecode.core.failure_category import FailureCategory
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError
from safecode.shell.risk import RiskLevel
from safecode.shell.runner import ShellRunner
from safecode.tools.gate import GateError, ToolCallGate
from safecode.utils.time import utc_now_iso
from safecode.task.wiring import (
    get_or_create_current_task,
    record_edit_on_task,
    record_apply_on_task,
    record_rollback_on_task,
    record_run_on_task,
)
from safecode.task.recovery import mark_task_interrupted

core_app = typer.Typer()
trust_app = typer.Typer(help="Manage session-local trust grants.")


def _apply_model_override(model: str) -> None:
    """Apply a one-shot model override via env var. Emits console feedback."""
    from safecode.cli_model import apply_model_override_env
    _, resolved, suggestion = apply_model_override_env(model)
    if suggestion:
        console.print(f"[yellow]{suggestion}[/yellow]")
    console.print(f"[dim]Session model override: {resolved}[/dim]")


@core_app.command()
def ask(
    question: str,
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    model: str = typer.Option("", "--model", help="One-shot model override (e.g. flash or deepseek:pro)."),
    stream: bool = typer.Option(False, "--stream", help="Stream token-by-token output (TTY only; non-TTY falls back to batch)."),
) -> None:
    """Ask a read-only question about the current project."""
    if model:
        _apply_model_override(model)
    project_root = Path.cwd()
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    orchestrator = AgentOrchestrator(project_root)

    if stream and is_tty and not json_output:
        try:
            from safecode.cli_stream import render_stream
            render_stream(orchestrator, question, is_tty=True)
        except Exception as exc:
            log_cli_error("cli.ask", "stream ask failed", exc)
            console.print(f"[red]Ask failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        return

    try:
        answer = orchestrator.ask(question)
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
    model: str = typer.Option("", "--model", help="One-shot model override (e.g. flash or deepseek:pro)."),
) -> None:
    """Create a pending patch proposal without modifying files."""
    if model:
        _apply_model_override(model)
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

    # Wire task sidecar (experimental)
    try:
        current_task = get_or_create_current_task(project_root, "edit", task)
    except Exception:
        current_task = None

    orchestrator = AgentOrchestrator(project_root)
    try:
        result = orchestrator.edit(effective_task)
    except KeyboardInterrupt:
        mark_task_interrupted(project_root, command_name="edit", hint=task, task_id=current_task.task_id if current_task else None)
        runtime_logger().error(
            "cli.edit",
            "edit interrupted",
            exc=KeyboardInterrupt(),
            failure_category=FailureCategory.INTERRUPTED.value,
            task_id=current_task.task_id if current_task else "",
        )
        if json_output:
            print(render_json(CLIJSONResponse(command="edit", status="error", error="Interrupted. resume with: sac resume")))
        else:
            console.print("[yellow]Interrupted. resume with: sac resume[/yellow]")
        raise typer.Exit(code=130)
    except (PatchParseError, PatchValidationError) as exc:
        log_cli_error("cli.edit", "patch proposal failed", exc, failure_category=FailureCategory.PATCH_PARSE_FAILED.value)
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

    # Record in task sidecar and audit with task_id metadata
    task_id = current_task.task_id if current_task else None
    if task_id:
        try:
            record_edit_on_task(project_root, task_id, result.proposal.id)
        except Exception:
            pass
    # Re-write the audit event with task_id in metadata
    if task_id:
        try:
            orchestrator.audit_logger.write(
                AuditEvent(
                    type="task_edit_wired",
                    timestamp=utc_now_iso(),
                    patch_id=result.proposal.id,
                    message=f"edit wired to task {task_id}",
                ),
                task_id=task_id,
            )
        except Exception:
            pass

    if json_output:
        print(render_json(CLIJSONResponse(
            command="edit",
            status="success",
            data={
                "pending_patch_path": str(result.pending_patch_path),
                "diff_text": result.diff_text,
                "task_id": task_id,
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
    allow_unrelated_changes: bool = typer.Option(False, "--allow-unrelated-changes", help="Bypass the dirty-tree guard."),
) -> None:
    """Apply the latest pending patch after review."""
    project_root = Path.cwd()
    orchestrator = AgentOrchestrator(project_root)

    try:
        preview = orchestrator.preview_apply()
    except (FileNotFoundError, PatchValidationError) as exc:
        log_cli_error("cli.apply", "apply preview failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=str(exc))))
        else:
            console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    try:
        from safecode.git.local import audit_dirty_refusal, current_task, dirty_tree_guard, is_git_repo, task_files

        if is_git_repo(project_root):
            task = current_task(project_root)
            allowed = {block.file_path.as_posix() for block in preview.proposal.blocks}
            if task is not None:
                allowed.update(task_files(project_root, task, include_pending=True))
            guard = dirty_tree_guard(project_root, allowed)
            if not guard.ok and not allow_unrelated_changes:
                audit_dirty_refusal(project_root, task.task_id if task else None, guard.unrelated_files, "apply")
                if json_output:
                    print(render_json(CLIJSONResponse(command="apply", status="error", error=guard.message)))
                else:
                    console.print(f"[red]Apply failed:[/red] {guard.message}")
                raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception:
        pass

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

    # Wire task sidecar (experimental)
    try:
        current_task_for_apply = get_or_create_current_task(project_root, "apply")
    except Exception:
        current_task_for_apply = None
    apply_task_id = current_task_for_apply.task_id if current_task_for_apply else None

    try:
        result = orchestrator.apply(preview.proposal)
    except PatchValidationError as exc:
        log_cli_error("cli.apply", "apply command failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=str(exc))))
        else:
            console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.apply", "apply command failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
        if json_output:
            print(render_json(CLIJSONResponse(command="apply", status="error", error=str(exc))))
        else:
            console.print(f"[red]Apply failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    # Record apply in task sidecar
    if apply_task_id:
        try:
            record_apply_on_task(project_root, apply_task_id, result.checkpoint.checkpoint_id)
            orchestrator.audit_logger.write(
                AuditEvent(
                    type="task_apply_wired",
                    timestamp=utc_now_iso(),
                    patch_id=result.proposal.id,
                    checkpoint_id=result.checkpoint.checkpoint_id,
                    message=f"apply wired to task {apply_task_id}",
                ),
                task_id=apply_task_id,
            )
        except Exception:
            pass

    if json_output:
        print(render_json(CLIJSONResponse(
            command="apply",
            status="success",
            data={
                "patch_id": result.proposal.id,
                "checkpoint_id": result.checkpoint.checkpoint_id,
                "files": list(result.files),
                "task_id": apply_task_id,
            },
        )))
        return
    console.print(
        Panel.fit(
            f"Applied patch {result.proposal.id}\n"
            f"Checkpoint: {result.checkpoint.checkpoint_id}\n"
            f"Hooks: {len(result.hooks.results) if result.hooks else 0}\n"
            f"Files: {', '.join(result.files)}\n"
            f"Undo: `sac rollback --last`",
            title="SafeCode",
        )
    )


def _perform_rollback_with_guards(
    project_root: Path,
    orchestrator: "AgentOrchestrator",
    metadata: "CheckpointMetadata",  # type: ignore[name-defined]  # noqa: F821
    *,
    force_uncommit: bool,
    use_rollback_last: bool,
) -> "RollbackResult":  # type: ignore[name-defined]  # noqa: F821
    """Shared guard logic for both --last and --checkpoint rollback paths.

    Runs ToolCallGate, committed-checkpoint detection, and task sidecar wiring
    for any rollback, regardless of which checkpoint is targeted.
    """
    # Gate: rollback is a write-class operation.
    gate_result = ToolCallGate().check_intent("checkpoint.rollback", approved=True)
    if not gate_result.allowed:
        console.print(f"[red]Blocked by tool gate:[/red] {gate_result.reason}")
        raise typer.Exit(code=1)

    # Wire task sidecar (best-effort)
    try:
        current_task_for_rollback = get_or_create_current_task(project_root, "rollback")
    except Exception:
        current_task_for_rollback = None
    rollback_task_id = current_task_for_rollback.task_id if current_task_for_rollback else None

    # Committed-checkpoint guard: check the *specific* checkpoint being rolled back.
    committed_sha: str | None = None
    if not force_uncommit:
        try:
            from safecode.git.local import commit_contains_files_or_checkpoint, is_git_repo, worktree_has_changes_for_files

            if is_git_repo(project_root):
                checkpoint_files = [operation.path for operation in metadata.file_operations]
                if not worktree_has_changes_for_files(project_root, checkpoint_files):
                    committed_sha = commit_contains_files_or_checkpoint(project_root, metadata)
                if committed_sha:
                    console.print(
                        "[red]Rollback refused:[/red] this apply appears committed. "
                        f"Use git revert {committed_sha} instead, or rerun with --force-uncommit."
                    )
                    raise typer.Exit(code=1)
        except typer.Exit:
            raise
        except Exception:
            pass

    # Perform the restore.
    if use_rollback_last:
        result = orchestrator.rollback_last()
    else:
        result = orchestrator.rollback_checkpoint(metadata.checkpoint_id)

    # Record rollback in task sidecar
    if rollback_task_id:
        try:
            record_rollback_on_task(project_root, rollback_task_id, result.checkpoint.checkpoint_id)
            if force_uncommit:
                try:
                    from safecode.git.local import commit_contains_files_or_checkpoint, is_git_repo

                    if is_git_repo(project_root):
                        committed_sha = commit_contains_files_or_checkpoint(project_root, result.checkpoint)
                except Exception:
                    committed_sha = None
                orchestrator.audit_logger.write(
                    AuditEvent(
                        type="rollback_force_uncommit",
                        timestamp=utc_now_iso(),
                        checkpoint_id=result.checkpoint.checkpoint_id,
                        message="rollback after committed apply forced",
                        metadata={"commit_sha": committed_sha or "unknown"},
                    ),
                    task_id=rollback_task_id,
                )
            orchestrator.audit_logger.write(
                AuditEvent(
                    type="task_rollback_wired",
                    timestamp=utc_now_iso(),
                    checkpoint_id=result.checkpoint.checkpoint_id,
                    message=f"rollback wired to task {rollback_task_id}",
                ),
                task_id=rollback_task_id,
            )
        except Exception:
            pass

    return result


@core_app.command(hidden=True)
def rollback(
    last: bool = typer.Option(False, "--last", help="Rollback the latest checkpoint."),
    force_uncommit: bool = typer.Option(False, "--force-uncommit", help="Dangerous: allow rollback after the apply appears committed."),
    checkpoint: str = typer.Option("", "--checkpoint", help="[EXPERIMENTAL v4.18] Rollback a specific checkpoint by ID."),
    list_checkpoints: bool = typer.Option(False, "--list", help="[EXPERIMENTAL v4.18] List available checkpoints."),
) -> None:
    """Rollback a previous applied patch."""
    from safecode.checkpoint.manager import CheckpointManager
    from safecode.checkpoint.models import CheckpointMetadata

    project_root = Path.cwd()

    if list_checkpoints:
        mgr = AgentOrchestrator(project_root).list_checkpoints()
        if not mgr:
            console.print("[yellow]No checkpoints found.[/yellow]")
        else:
            table = Table(title="Checkpoints")
            table.add_column("ID")
            table.add_column("Patch")
            table.add_column("Task")
            table.add_column("Files")
            for c in mgr:
                table.add_row(
                    c.checkpoint_id,
                    c.patch_id,
                    c.task[:60] if c.task else "",
                    ", ".join(op.path for op in c.file_operations),
                )
            console.print(table)
        raise typer.Exit(code=0)

    if checkpoint:
        orch = AgentOrchestrator(project_root)
        try:
            metadata = CheckpointManager(project_root)._load_metadata(checkpoint)
        except FileNotFoundError as exc:
            log_cli_error("cli.rollback", "rollback failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
            console.print(f"[red]Rollback failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        try:
            result = _perform_rollback_with_guards(
                project_root, orch, metadata,
                force_uncommit=force_uncommit,
                use_rollback_last=False,
            )
        except typer.Exit:
            raise
        except Exception as exc:
            log_cli_error("cli.rollback", "rollback failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
            console.print(f"[red]Rollback failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(
            Panel.fit(
                f"Rolled back checkpoint: {result.checkpoint.checkpoint_id}\n"
                f"Files: {', '.join(result.files)}",
                title="SafeCode",
            )
        )
        raise typer.Exit(code=0)

    if not last:
        console.print("[red]Use --last, --checkpoint <id>, or --list.[/red]")
        raise typer.Exit(code=1)

    orch = AgentOrchestrator(project_root)
    try:
        metadata = CheckpointManager(project_root)._load_latest_metadata()
    except FileNotFoundError as exc:
        log_cli_error("cli.rollback", "rollback failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
        console.print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    try:
        result = _perform_rollback_with_guards(
            project_root, orch, metadata,
            force_uncommit=force_uncommit,
            use_rollback_last=True,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        log_cli_error("cli.rollback", "rollback failed", exc, failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value)
        console.print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Rolled back checkpoint: {result.checkpoint.checkpoint_id}\n"
            f"Files: {', '.join(result.files)}",
            title="SafeCode",
        )
    )


@core_app.command(hidden=True)
def history(
    task: Optional[str] = typer.Option(
        None, "--task", help="[EXPERIMENTAL] Filter by task id (exact match on metadata.task_id).",
    ),
) -> None:
    """Show recent SafeCode Agent audit events."""
    events = AgentOrchestrator(Path.cwd()).history()

    # Apply --task filter if specified (experimental, v4.1.2)
    if task is not None:
        events = [e for e in events if e.metadata.get("task_id") == task]

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


@trust_app.command("grant")
def trust_grant(
    path: str = typer.Argument(".", help="Directory to trust for this session."),
    until_end_of_session: bool = typer.Option(
        False,
        "--until-end-of-session",
        help="Grant process-local trust only; never persists to config.",
    ),
    policy: str = typer.Option("balanced", "--policy", help="Trust policy: strict, balanced, experimental."),
) -> None:
    """Grant trust for this process only."""
    if not until_end_of_session:
        console.print("[red]Trust grants must be ephemeral in v3.11.0: pass --until-end-of-session.[/red]")
        raise typer.Exit(1)
    project_root = Path.cwd()
    grant_id = grant_ephemeral_trust(Path(path), policy)
    AuditLogger(project_root).write(
        AuditEvent(
            type="ephemeral_trust_granted",
            timestamp=utc_now_iso(),
            status="success",
            message="Ephemeral trust granted until process exit.",
            metadata={
                "grant_id": grant_id,
                "path": str(Path(path).expanduser().resolve()),
                "policy": policy,
                "persisted": "false",
            },
        )
    )
    console.print(f"Ephemeral trust granted: {grant_id}")


@trust_app.command("revoke")
def trust_revoke(grant_id: str) -> None:
    """Revoke a session-local trust grant."""
    project_root = Path.cwd()
    revoked = revoke_ephemeral_trust(grant_id)
    AuditLogger(project_root).write(
        AuditEvent(
            type="ephemeral_trust_revoked",
            timestamp=utc_now_iso(),
            status="success" if revoked else "blocked",
            message="Ephemeral trust revoked." if revoked else "Ephemeral trust grant not found.",
            metadata={"grant_id": grant_id, "persisted": "false"},
        )
    )
    if not revoked:
        console.print("[yellow]No matching ephemeral trust grant.[/yellow]")
        raise typer.Exit(1)
    console.print(f"Ephemeral trust revoked: {grant_id}")


@core_app.command("run", hidden=True)
def run_command(
    command: Optional[str] = typer.Argument(None, help="Shell command to run."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve medium/high risk commands."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    model: str = typer.Option("", "--model", help="One-shot model override (e.g. flash or deepseek:pro)."),
    suite: Optional[str] = typer.Option(
        None, "--suite",
        help="[EXPERIMENTAL] Run a project profile suite: test|lint|typecheck|build. (v4.2+)",
    ),
) -> None:
    """Run a shell command through SafeCode risk checks."""
    if model:
        _apply_model_override(model)
    from safecode.project.profile import load_profile, _VALID_KINDS

    project_root = Path.cwd()

    # Resolve the effective command string
    if suite is not None:
        # --suite mode (EXPERIMENTAL, v4.2+)
        if suite not in _VALID_KINDS:
            msg = f"Unknown suite kind: {suite!r}. Must be one of: {sorted(_VALID_KINDS)}"
            if json_output:
                print(render_json(CLIJSONResponse(command="run", status="error", error=msg)))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(code=1)

        profile = load_profile(project_root)
        if profile is None:
            msg = "No project profile found. Run 'sac profile detect' first."
            if json_output:
                print(render_json(CLIJSONResponse(command="run", status="error", error=msg)))
            else:
                console.print(f"[yellow]{msg}[/yellow]")
            raise typer.Exit(code=1)

        suite_cmd = getattr(profile, suite)
        if suite_cmd is None:
            msg = (
                f"No '{suite}' command in project profile. "
                f"Run 'sac profile detect' or 'sac profile set {suite} \"<cmd>\"'."
            )
            if json_output:
                print(render_json(CLIJSONResponse(command="run", status="error", error=msg)))
            else:
                console.print(f"[yellow]{msg}[/yellow]")
            raise typer.Exit(code=1)

        command = " ".join(suite_cmd.command)
        # Suite commands are pre-approved by the user's explicit selection; treat as --yes
        yes = True
        if not json_output:
            console.print(f"[blue]Suite '{suite}':[/blue] {command}")
    elif command is None:
        msg = "Either provide a COMMAND argument or use --suite <kind>."
        if json_output:
            print(render_json(CLIJSONResponse(command="run", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

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

    # Wire task sidecar (experimental)
    try:
        current_task_for_run = get_or_create_current_task(project_root, "run", command)
    except Exception:
        current_task_for_run = None
    run_task_id = current_task_for_run.task_id if current_task_for_run else None

    try:
        result = runner.run(command, approved=approved)
    except KeyboardInterrupt:
        mark_task_interrupted(project_root, command_name="run", hint=command, task_id=run_task_id)
        runtime_logger().error(
            "cli.run",
            "run interrupted",
            exc=KeyboardInterrupt(),
            failure_category=FailureCategory.INTERRUPTED.value,
            command=command or "",
            task_id=run_task_id or "",
        )
        if json_output:
            print(render_json(CLIJSONResponse(command="run", status="error", error="Interrupted. resume with: sac resume")))
        else:
            console.print("[yellow]Interrupted. resume with: sac resume[/yellow]")
        raise typer.Exit(code=130)
    runtime_logger().info(
        "cli.run",
        "shell command evaluated",
        command=command,
        exit_code=str(result.exit_code),
        executed=str(result.executed),
        risk=str(result.risk.level),
    )
    if result.exit_code != 0:
        if result.exit_code == 124:
            category = FailureCategory.COMMAND_TIMEOUT.value
        elif not result.executed and result.exit_code in {125, 126}:
            category = FailureCategory.NETWORK_DISABLED.value if "network" in (result.stderr or "").lower() else FailureCategory.COMMAND_BLOCKED_BY_POLICY.value
        elif result.exit_code == 127:
            category = FailureCategory.DEPENDENCY_MISSING.value
        else:
            category = FailureCategory.UNKNOWN.value
        runtime_logger().write(
            "error",
            "cli.run",
            "shell command failed",
            failure_category=category,
            details={
                "command": command or "",
                "exit_code": str(result.exit_code),
                "executed": str(result.executed),
                "task_id": run_task_id or "",
            },
        )
    run_orchestrator = AgentOrchestrator(project_root)
    run_orchestrator.audit_logger.write(
        AuditEvent(
            type="shell_completed" if result.executed else "shell_blocked",
            timestamp=utc_now_iso(),
            status="success" if result.exit_code == 0 else "failed",
            command=command,
            exit_code=result.exit_code,
            message=f"risk={result.risk.level}; duration_ms={result.duration_ms}",
        ),
        task_id=run_task_id,
    )
    # Record run in task sidecar
    if run_task_id:
        try:
            record_run_on_task(project_root, run_task_id, command, result.exit_code)
        except Exception:
            pass

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
