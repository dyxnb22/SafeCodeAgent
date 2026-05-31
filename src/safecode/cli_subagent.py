from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint

from safecode.subagents.merge import SubagentMergeReviewer
from safecode.subagents.runner import ReadonlySubagentRunner
from safecode.subagents.task import SubagentTaskStore

subagent_app = typer.Typer(
    help=(
        "Create and run file-backed subagent tasks.\n\n"
        "[dim]Current subagents are read-only context/result collectors: they collect "
        "project context and write a result file under .sac/subagents/. "
        "They are not independent LLM investigations.[/dim]"
    )
)


@subagent_app.command("create")
def subagent_create(title: str, instructions: str, write: bool = typer.Option(False, "--write")) -> None:
    """Create a file-backed subagent task."""
    task = SubagentTaskStore(Path.cwd()).create(title, instructions, readonly=not write)
    console.print(f"Subagent task created: {task.id}")


@subagent_app.command("run-readonly")
def subagent_run_readonly(
    title: str,
    instructions: str,
) -> None:
    """Run a read-only subagent task (context/result collector).

    Collects project context and writes a result file under .sac/subagents/.
    Subagents are read-only context/result collectors, not independent LLM investigations.
    """
    project_root = Path.cwd()
    try:
        result = ReadonlySubagentRunner(project_root).run(title, instructions)
    except Exception as exc:
        log_cli_error("cli.subagent.run_readonly", "subagent run failed", exc)
        console.print(f"[red]Subagent run failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Task ID: {result.task.id}\n"
            f"Status: {result.task.status}\n"
            f"Result: {result.result_path}\n\n"
            "[dim]This subagent collected read-only context/result. "
            "No independent LLM investigation was performed.[/dim]",
            title="Subagent Read-only Run",
        )
    )


@subagent_app.command("list")
def subagent_list() -> None:
    """List subagent tasks."""
    project_root = Path.cwd()
    tasks = SubagentTaskStore(project_root).list_tasks()

    if not tasks:
        console.print("[yellow]No subagent tasks found.[/yellow]")
        return

    table = Table(title="Subagent Tasks")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Readonly")
    table.add_column("Created")
    for task in tasks:
        table.add_row(
            task.id,
            task.title[:60],
            task.status,
            "yes" if task.readonly else "no",
            task.created_at[:19],
        )
    console.print(table)


@subagent_app.command("show")
def subagent_show(task_id: str) -> None:
    """Show a subagent task and its result."""
    project_root = Path.cwd()
    store = SubagentTaskStore(project_root)
    task = store.get_task(task_id)

    if task is None:
        console.print(f"[red]Subagent task not found: {task_id}[/red]")
        raise typer.Exit(code=1)

    table = Table(title=f"Subagent Task: {task.id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("ID", task.id)
    table.add_row("Title", task.title)
    table.add_row("Instructions", task.instructions[:120])
    table.add_row("Readonly", "yes" if task.readonly else "no")
    table.add_row("Status", task.status)
    table.add_row("Created", task.created_at)
    if task.started_at:
        table.add_row("Started", task.started_at)
    if task.completed_at:
        table.add_row("Completed", task.completed_at)
    if task.result_path:
        table.add_row("Result Path", task.result_path)
    if task.error:
        table.add_row("Error", task.error)
    console.print(table)

    result_path = store.result_path_for(task.id)
    if result_path.exists():
        console.print(f"\n[bold]Result file:[/bold] {result_path}")
        console.print(result_path.read_text(encoding="utf-8")[:500])
    else:
        console.print("\n[yellow]No result file yet.[/yellow]")


@subagent_app.command("merge-review")
def subagent_merge_review(
    task_ids: list[str] = typer.Argument(..., help="Completed subagent task IDs to merge."),
    target: str = typer.Option("SUBAGENT_REVIEW.md", "--target", "-t", help="Target markdown file with merge marker."),
) -> None:
    """Create a pending patch proposal from completed subagent results."""
    project_root = Path.cwd()

    try:
        result = SubagentMergeReviewer(project_root).propose(task_ids, target)
    except (FileNotFoundError, ValueError, PermissionError, FileExistsError) as exc:
        log_cli_error("cli.subagent.merge_review", "merge review blocked", exc)
        console.print(f"[red]Merge review blocked:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        log_cli_error("cli.subagent.merge_review", "merge review failed", exc)
        console.print(f"[red]Merge review failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Patch ID: {result.proposal.id}\n"
            f"Tasks merged: {len(task_ids)}\n"
            f"Target: {target}\n"
            f"Pending patch: {result.pending_path}",
            title="Subagent Merge Review",
        )
    )
    console.print(Syntax(result.diff_text, "diff", theme="ansi_dark"))
    console.print("[green]Review the diff above. Run 'sac apply' to apply the merge.[/green]")


