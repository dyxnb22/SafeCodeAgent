"""Experimental local Git delivery commands for v4.5."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.syntax import Syntax

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.context.redactor import redact_secrets
from safecode.llm.factory import create_llm_client
from safecode.patch.diff import build_unified_diff
from safecode.git.local import (
    GitError,
    add_files,
    audit_dirty_refusal,
    commit,
    create_and_switch_branch,
    current_task,
    diff_for_files,
    dirty_tree_guard,
    is_git_repo,
    pending_patch,
    staged_files,
    task_files,
)


branch_app = typer.Typer(help="Experimental local branch helpers.")
diff_app = typer.Typer(help="Experimental task diff helpers.")


def _json_or_print(command: str, json_output: bool, status: str, data: dict, error: str | None = None) -> None:
    if json_output:
        print(render_json(CLIJSONResponse(command=command, status=status, data=data, error=error)))


def _require_repo(project_root: Path) -> None:
    if not is_git_repo(project_root):
        raise GitError("Not a git repository. sac commit is local-git only.")


def _commit_message(goal: str, task_id: str, include_summary: bool, iterations: list[object]) -> str:
    subject = " ".join(goal.strip().split())[:72] or f"SafeCode task {task_id}"
    body = [subject, "", f"Task: {task_id}"]
    if include_summary:
        body.append("")
        body.append("Iteration trail:")
        for iteration in iterations:
            event = getattr(iteration, "event", "")
            status = getattr(iteration, "status", None)
            suffix = f" ({status})" if status else ""
            body.append(f"- {event}{suffix}")
    return "\n".join(body)


def _generate_ai_commit_message(project_root: Path, task_goal: str, files: list[str]) -> str:
    """Call the configured LLM to generate a conventional-commit message.

    Collects a capped git diff and asks the LLM to produce:
      type(scope): subject
      <blank line>
      body (optional)

    Returns the raw message text. Never raises — callers catch exceptions.
    """
    from safecode.config import SafeCodeConfig
    from safecode.agent.schemas import AgentAnswer

    config = SafeCodeConfig.load(project_root)
    llm = create_llm_client(config)

    # Collect a compact diff (capped to keep prompt reasonable).
    try:
        raw_diff = diff_for_files(project_root, files) or ""
    except Exception:
        raw_diff = ""
    diff_snippet = redact_secrets(raw_diff)[:4000]

    file_list = "\n".join(f"  - {f}" for f in files[:30])
    if len(files) > 30:
        file_list += f"\n  ... and {len(files) - 30} more"

    prompt = (
        "Generate a conventional-commit message for the following code change.\n\n"
        "Format:\n"
        "  type(scope): short subject (≤72 chars)\n"
        "  <blank line>\n"
        "  Optional body (concise, explain WHY not WHAT, max 3 sentences).\n\n"
        "Types: feat, fix, refactor, docs, test, chore, perf, style.\n"
        "Be specific. Do not include 'Co-authored-by' lines.\n\n"
        f"Task goal: {task_goal}\n\n"
        f"Files changed:\n{file_list}\n\n"
        f"Diff (may be truncated):\n```diff\n{diff_snippet}\n```"
    )
    result = llm.ask(prompt, {})
    if not isinstance(result, AgentAnswer) or not result.content:
        raise ValueError("LLM returned empty commit message")
    return result.content.strip()


def register(app: typer.Typer) -> None:
    @app.command("commit")
    def commit_cmd(
        message_from_task: bool = typer.Option(False, "--message-from-task", help="Use the task goal as the commit subject."),
        ai_message: bool = typer.Option(False, "--ai", help="[v6.28] Use AI to generate a conventional commit message."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Print the commit message without committing (for --ai)."),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (for --ai)."),
        branch: Optional[str] = typer.Option(None, "--branch", help="Create and switch to this local branch before committing."),
        include_task_summary: bool = typer.Option(False, "--include-task-summary", help="Include an iteration trail in the commit body."),
        allow_unrelated_changes: bool = typer.Option(False, "--allow-unrelated-changes", help="Bypass the dirty-tree guard."),
        json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    ) -> None:
        """EXPERIMENTAL: commit only files touched by the current task."""
        project_root = Path.cwd()
        try:
            _require_repo(project_root)
            task = current_task(project_root)
            if task is None:
                raise GitError("No current task found. Run sac task new or sac edit first.")
            files = task_files(project_root, task)
            if not files:
                raise GitError("Could not determine files for current task; refusing to commit.")
            guard = dirty_tree_guard(project_root, set(files))
            if not guard.ok and not allow_unrelated_changes:
                audit_dirty_refusal(project_root, task.task_id, guard.unrelated_files, "commit")
                raise GitError(guard.message)
            if branch:
                create_and_switch_branch(project_root, branch)
            add_files(project_root, list(files))
            staged = staged_files(project_root)
            unrelated_staged = sorted(set(staged) - set(files))
            if unrelated_staged:
                raise GitError(f"Refusing to commit unrelated staged files: {', '.join(unrelated_staged)}")

            # v6.28: AI-generated commit message path.
            if ai_message:
                try:
                    generated = _generate_ai_commit_message(project_root, task.goal, list(files))
                except Exception as exc:
                    err = redact_secrets(str(exc))
                    if json_output:
                        _json_or_print("commit", True, "error", {}, f"AI message generation failed: {err}. Use --message-from-task instead.")
                    else:
                        console.print(f"[red]AI message generation failed:[/red] {err}")
                        console.print("[yellow]Hint: use --message-from-task as a fallback.[/yellow]")
                    raise typer.Exit(code=1) from exc

                if dry_run:
                    if json_output:
                        _json_or_print("commit", True, "success", {"dry_run": True, "message": generated, "files": list(files)})
                    else:
                        console.print("[bold]Generated commit message (--dry-run, not committed):[/bold]")
                        console.print(generated)
                    return

                if not yes and not json_output:
                    console.print("[bold]Generated commit message:[/bold]")
                    console.print(generated)
                    confirm = console.input("\nCommit with this message? [y/N] ").strip().lower()
                    if confirm not in ("y", "yes"):
                        console.print("[yellow]Commit cancelled.[/yellow]")
                        raise typer.Exit(code=0)

                message = generated
            else:
                message = _commit_message(task.goal if message_from_task else task.goal, task.task_id, include_task_summary, list(task.iterations))

            output = commit(project_root, message)
        except GitError as exc:
            if json_output:
                _json_or_print("commit", True, "error", {}, str(exc))
            else:
                console.print(f"[red]Commit failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        data = {"task_id": task.task_id, "files": list(files), "git_output": redact_secrets(output)}
        if json_output:
            _json_or_print("commit", True, "success", data)
            return
        console.print(f"[green]Committed task {task.task_id}[/green]")
        console.print("\n".join(files))

    app.add_typer(branch_app, name="branch", hidden=True)

    @app.command("diff", hidden=True)
    def diff_cmd(
        task: bool = typer.Option(False, "--task", help="Show applied and pending changes for a task."),
        task_id: Optional[str] = typer.Argument(None),
        json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    ) -> None:
        """EXPERIMENTAL: read-only local diff helpers."""
        if not task:
            if json_output:
                _json_or_print("diff", True, "error", {}, "Only sac diff --task is available.")
            else:
                console.print("[red]Only sac diff --task is available.[/red]")
            raise typer.Exit(code=1)
        _run_diff_task(task_id, json_output=json_output)


@branch_app.command("new")
def branch_new(
    name: str,
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """EXPERIMENTAL: create and switch to a new local branch."""
    from safecode.git.local import create_and_switch_branch

    project_root = Path.cwd()
    try:
        _require_repo(project_root)
        guard = dirty_tree_guard(project_root, set())
        if not guard.ok:
            audit_dirty_refusal(project_root, None, guard.unrelated_files, "branch new")
            raise GitError(guard.message)
        create_and_switch_branch(project_root, name)
    except GitError as exc:
        if json_output:
            _json_or_print("branch new", True, "error", {}, str(exc))
        else:
            console.print(f"[red]Branch failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    data = {"branch": name}
    if json_output:
        _json_or_print("branch new", True, "success", data)
        return
    console.print(f"[green]Created branch {name}[/green]")


def _run_diff_task(task_id: Optional[str], *, json_output: bool) -> None:
    """EXPERIMENTAL: show current or selected task changes relative to HEAD."""
    project_root = Path.cwd()
    try:
        _require_repo(project_root)
        from safecode.task.store import TaskStore

        store = TaskStore(project_root)
        resolved_id = task_id or store.current_id()
        task = store.load(resolved_id) if resolved_id else None
        if task is None:
            data = {"task_id": resolved_id, "files": [], "diff": ""}
        else:
            files = task_files(project_root, task, include_pending=True)
            diff_parts: list[str] = []
            applied_diff = diff_for_files(project_root, list(files))
            if applied_diff:
                diff_parts.append(applied_diff)
            patch = pending_patch(project_root)
            if patch is not None:
                try:
                    pending_diff = build_unified_diff(project_root, patch)
                    if pending_diff:
                        diff_parts.append(pending_diff)
                except Exception:
                    pass
            diff_text = redact_secrets("\n".join(diff_parts))
            data = {"task_id": task.task_id, "files": list(files), "diff": diff_text}
    except GitError as exc:
        if json_output:
            _json_or_print("diff --task", True, "error", {}, str(exc))
        else:
            console.print(f"[red]Diff failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if json_output:
        _json_or_print("diff --task", True, "success", data)
        return
    if not data["files"]:
        console.print("No task changes.")
        return
    console.print(f"Task diff: {data['task_id']}")
    console.print("\n".join(data["files"]))
    # v6.27: Rich per-file diff panels.
    try:
        from safecode.cli_diff_render import render_rich_diff
        render_rich_diff(data["diff"], title="Task diff", console=console)
    except Exception:
        console.print(Syntax(data["diff"], "diff", theme="ansi_dark"))
