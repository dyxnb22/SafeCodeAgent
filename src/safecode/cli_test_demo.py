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
from safecode.demo.workflows import DemoWorkflow, DemoWorkflowSuite
from safecode.project.test_detector import ProjectTestDetector, TestCommandCandidate
from safecode.shell.risk import RiskLevel
from safecode.shell.runner import ShellRunner
from safecode.utils.time import utc_now_iso

test_app = typer.Typer(help="Detect and run project tests through SafeCode policy.")
demo_app = typer.Typer(help="Inspect and materialize repeatable demo workflows.")


def _render_test_candidates(project_root: Path, candidates: list[TestCommandCandidate]) -> None:
    """Render detected test commands and policy proposal status."""
    if not candidates:
        console.print("[yellow]No test command candidates detected.[/yellow]")
        return

    runner = ShellRunner(project_root)
    table = Table(title="SafeCode Test Commands")
    table.add_column("#")
    table.add_column("Command")
    table.add_column("Tool")
    table.add_column("Confidence")
    table.add_column("Policy")
    table.add_column("Reason")
    for index, candidate in enumerate(candidates):
        proposal = runner.propose(candidate.command)
        table.add_row(
            str(index),
            candidate.command,
            candidate.tool,
            candidate.confidence,
            proposal.status,
            f"{candidate.reason} {proposal.decision.reason}",
        )
    console.print(table)


def _select_test_candidate(project_root: Path, candidates: list[TestCommandCandidate], index: int) -> TestCommandCandidate:
    if index != 0:
        if index >= len(candidates):
            raise IndexError(index)
        return candidates[index]

    runner = ShellRunner(project_root)
    for candidate in candidates:
        if runner.propose(candidate.command).status != "blocked":
            return candidate
    return candidates[0]


def _render_demo_workflows(workflows: list[DemoWorkflow]) -> None:
    """Render demo workflows in a compact table."""
    table = Table(title="SafeCode Demo Workflows")
    table.add_column("ID", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Title")
    table.add_column("Task")
    for workflow in workflows:
        table.add_row(workflow.id, workflow.category, workflow.title, workflow.task)
    console.print(table)


@test_app.command("detect")
def test_detect() -> None:
    """Detect likely project test commands without executing them."""
    project_root = Path.cwd()
    candidates = ProjectTestDetector(project_root).detect()
    _render_test_candidates(project_root, candidates)


@test_app.command("run")
def test_run(
    command: Optional[str] = typer.Option(None, "--command", "-c", help="Run an explicit test command."),
    index: int = typer.Option(0, "--index", min=0, help="Detected command index to run."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve medium-risk test commands."),
) -> None:
    """Run a detected test command through SafeCode policy checks."""
    project_root = Path.cwd()
    candidates = ProjectTestDetector(project_root).detect()
    if command is None:
        if not candidates:
            console.print("[yellow]No test command candidates detected.[/yellow]")
            raise typer.Exit(code=1)
        try:
            selected = _select_test_candidate(project_root, candidates, index)
        except IndexError:
            console.print(f"[red]No test command candidate at index {index}.[/red]")
            raise typer.Exit(code=1)
        command = selected.command

    runner = ShellRunner(project_root)
    proposal = runner.propose(command)
    risk = proposal.decision.risk
    console.print(Panel.fit("\n".join([f"Command: {command}", f"Policy: {proposal.status}", *risk.reasons]), title="Test Command"))

    approved = yes
    if risk.level == RiskLevel.MEDIUM and proposal.decision.requires_approval and not yes:
        checkpoint = HumanCheckpointPresenter(project_root).checkpoint(
            checkpoint_type="test_run",
            title="Test Command Checkpoint",
            prompt="Run this test command?",
            risk_level=str(risk.level),
            summary=f"Run test command through SafeCode policy: {command}",
            subject=command,
            metadata={
                "command_head": risk.tokens[0] if risk.tokens else "",
                "detected": str(command in [candidate.command for candidate in candidates]),
            },
        )
        show_human_checkpoint(checkpoint)
        approved = typer.confirm(checkpoint.prompt, default=False)
    if risk.level == RiskLevel.HIGH:
        console.print("[red]High-risk test command blocked by policy.[/red]")
        approved = False

    result = runner.run(command, approved=approved)
    runtime_logger().info(
        "cli.test.run",
        "test command evaluated",
        command=command,
        exit_code=str(result.exit_code),
        executed=str(result.executed),
        risk=str(result.risk.level),
    )
    AgentOrchestrator(project_root).audit_logger.write(
        AuditEvent(
            type="test_completed" if result.executed else "test_blocked",
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


@demo_app.command("list")
def demo_list() -> None:
    """List built-in repeatable demo workflows."""
    _render_demo_workflows(DemoWorkflowSuite().list())


@demo_app.command("show")
def demo_show(workflow_id: str) -> None:
    """Show one demo workflow's task, files, and commands."""
    try:
        workflow = DemoWorkflowSuite().get(workflow_id)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    lines = [
        workflow.description,
        "",
        f"Task: {workflow.task}",
        f"Files: {', '.join(workflow.expected_files)}",
        f"Commands: {' -> '.join(workflow.commands)}",
        "",
        "Acceptance:",
        *[f"- {item}" for item in workflow.acceptance],
    ]
    console.print(Panel.fit("\n".join(lines), title=workflow.title))


@demo_app.command("materialize")
def demo_materialize(
    workflow_id: str,
    destination: Path = typer.Option(Path("examples/demo-workflows"), "--destination", "-d"),
    force: bool = typer.Option(False, "--force", help="Overwrite files in an existing demo directory."),
) -> None:
    """Create a local seed project for one demo workflow."""
    try:
        project_root = DemoWorkflowSuite().materialize(workflow_id, destination, force=force)
    except (KeyError, FileExistsError, PermissionError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(Panel.fit(f"Demo workflow created: {project_root}", title="SafeCode Demo"))


