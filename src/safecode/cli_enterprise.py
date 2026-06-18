"""Enterprise CLI commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.workflow.checkpoint import gc_runs
from safecode.enterprise.approvals.store import (
    decide_request,
    list_pending_requests,
    list_requests,
    load_request,
    request_evidence,
    revoke_request,
)
from safecode.enterprise.approvals.cli_render import render_pending_requests
from safecode.enterprise.rbac.models import resolve_subject
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestNotFoundError,
    RequestAlreadyConsumedError,
    WorkflowError,
    WorkflowInterrupted,
)
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType

RAG_MAX_CITATIONS = 8

enterprise_app = typer.Typer(help="Enterprise security workflow commands.")
workflow_app = typer.Typer(help="Enterprise workflow orchestration.")
approval_app = typer.Typer(help="Enterprise approval inbox.")
enterprise_app.add_typer(workflow_app, name="workflow")
enterprise_app.add_typer(approval_app, name="approval")


@enterprise_app.command("retrieve")
def retrieve(
    query: list[str] = typer.Argument(..., help="Retrieval query words."),
    manifest: Path = typer.Option(
        Path("examples/enterprise/knowledge_sources.yaml"),
        "--manifest",
        help="Knowledge source manifest path.",
    ),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    actor_scope: str = typer.Option("org", "--actor-scope", help="Comma-separated actor scope tags."),
    actor_tenant: str = typer.Option("local", "--actor-tenant", help="Actor tenant id."),
    k: int = typer.Option(RAG_MAX_CITATIONS, "--k", min=1, max=RAG_MAX_CITATIONS),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Print JSON citations."),
) -> None:
    """Retrieve cited knowledge chunks from the enterprise manifest (read-only)."""
    project_root = (root or Path.cwd()).resolve()
    scope = [part.strip() for part in actor_scope.split(",") if part.strip()]
    query_text = " ".join(query).strip()
    chunks = build_chunks_from_manifest(manifest, project_root)
    retriever = HybridRetriever(chunks=chunks)
    citations = retriever.retrieve(
        query_text,
        min(k, RAG_MAX_CITATIONS),
        scope,
        actor_tenant=actor_tenant,
    )
    if json_output:
        typer.echo(json.dumps([item.model_dump(mode="json") for item in citations], indent=2))
    raise typer.Exit(code=0 if citations else 2)


@workflow_app.command("run")
def workflow_run(
    task: str = typer.Option(..., "--task", help="Workflow task type."),
    input_path: Path = typer.Option(..., "--input", help="Task input fixture path."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    actor: str = typer.Option("user:local", "--actor", help="Actor identifier."),
    as_role: Optional[str] = typer.Option(
        None, "--as-role", help="Override role when org policy allows."
    ),
    config_root: Optional[Path] = typer.Option(
        None, "--config-root", help="Enterprise config root."
    ),
) -> None:
    """Start a local enterprise workflow run."""
    project_root = (root or Path.cwd()).resolve()
    sac_root = project_root / ".sac"
    try:
        task_type = TaskType(task)
    except ValueError as exc:
        typer.echo("Unsupported task type.", err=True)
        raise typer.Exit(code=1) from exc
    try:
        resolve_subject(actor, config_root=config_root, as_role=as_role)
    except PermissionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    state = build_initial_state(
        task_type=task_type,
        input_ref=str(input_path),
        actor_id=actor,
        repo_root=project_root,
    )
    run_id = state.run_id
    orchestrator = LocalOrchestrator(sac_root)
    try:
        final = asyncio.run(orchestrator.run(state))
    except WorkflowInterrupted:
        typer.echo(json.dumps({"run_id": run_id, "status": "awaiting_approval"}))
        raise typer.Exit(code=3)
    except WorkflowError as exc:
        typer.echo("Workflow failed.", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"run_id": final.run_id, "status": final.status.value}))
    raise typer.Exit(code=0)


@workflow_app.command("resume")
def workflow_resume(
    run_id: str = typer.Argument(..., help="Run identifier."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    """Resume an interrupted workflow run."""
    project_root = (root or Path.cwd()).resolve()
    sac_root = project_root / ".sac"
    orchestrator = LocalOrchestrator(sac_root)
    try:
        final = asyncio.run(orchestrator.resume(run_id))
    except WorkflowInterrupted:
        typer.echo(json.dumps({"run_id": run_id, "status": "awaiting_approval"}))
        raise typer.Exit(code=3)
    except WorkflowError:
        typer.echo("Unable to resume workflow.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"run_id": final.run_id, "status": final.status.value}))
    raise typer.Exit(code=0)


@workflow_app.command("gc")
def workflow_gc(
    older_than: str = typer.Option(..., "--older-than", help="Retention window like 7d."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    """Remove stale workflow run directories under .sac/enterprise/runs."""
    if not older_than.endswith("d"):
        typer.echo("Only day-based retention like 7d is supported.", err=True)
        raise typer.Exit(code=1)
    days = int(older_than[:-1])
    project_root = (root or Path.cwd()).resolve()
    removed = gc_runs(project_root / ".sac", older_than_days=days)
    typer.echo(json.dumps({"removed": removed}))
    raise typer.Exit(code=0)


@approval_app.command("list")
def approval_list(
    run_id: str = typer.Argument(..., help="Run identifier."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    pending: bool = typer.Option(False, "--pending", help="Show only pending requests."),
    markdown: bool = typer.Option(False, "--markdown", help="Render pending requests as Markdown."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    requests = (
        list_pending_requests(project_root / ".sac", run_id)
        if pending
        else list_requests(project_root / ".sac", run_id)
    )
    if markdown:
        typer.echo(render_pending_requests(requests))
        raise typer.Exit(code=0)
    typer.echo(json.dumps([item.model_dump(mode="json") for item in requests], indent=2))
    raise typer.Exit(code=0)


@approval_app.command("show")
def approval_show(
    run_id: str = typer.Argument(..., help="Run identifier."),
    request_id: str = typer.Argument(..., help="Approval request identifier."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    try:
        request = load_request(project_root / ".sac", run_id, request_id)
    except ApprovalRequestNotFoundError:
        typer.echo("Approval request not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(request.model_dump_json(indent=2))
    raise typer.Exit(code=0)


@approval_app.command("approve")
def approval_approve(
    run_id: str = typer.Argument(..., help="Run identifier."),
    request_id: str = typer.Argument(..., help="Approval request identifier."),
    actor: str = typer.Option(..., "--actor", help="Human approver actor id."),
    note: str = typer.Option("", "--note", help="Optional approval note."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    try:
        request = decide_request(
            project_root / ".sac",
            run_id,
            request_id,
            decision="approved",
            decision_actor=actor,
            decision_note=note,
        )
    except RequestAlreadyConsumedError:
        typer.echo("Approval request already consumed.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"request_id": request.request_id, "status": request.status}))
    raise typer.Exit(code=0)


@approval_app.command("reject")
def approval_reject(
    run_id: str = typer.Argument(..., help="Run identifier."),
    request_id: str = typer.Argument(..., help="Approval request identifier."),
    actor: str = typer.Option(..., "--actor", help="Human approver actor id."),
    reason: str = typer.Option("", "--reason", help="Rejection reason."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    try:
        request = decide_request(
            project_root / ".sac",
            run_id,
            request_id,
            decision="rejected",
            decision_actor=actor,
            decision_note=reason,
        )
    except RequestAlreadyConsumedError:
        typer.echo("Approval request already consumed.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"request_id": request.request_id, "status": request.status}))
    raise typer.Exit(code=0)


@approval_app.command("request-evidence")
def approval_request_evidence(
    run_id: str = typer.Argument(..., help="Run identifier."),
    request_id: str = typer.Argument(..., help="Approval request identifier."),
    actor: str = typer.Option(..., "--actor", help="Human approver actor id."),
    note: str = typer.Option(..., "--note", help="Evidence request note."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    try:
        request = request_evidence(
            project_root / ".sac",
            run_id,
            request_id,
            decision_actor=actor,
            decision_note=note,
        )
    except (RequestAlreadyConsumedError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"request_id": request.request_id, "status": request.status}))
    raise typer.Exit(code=0)


@approval_app.command("revoke")
def approval_revoke(
    run_id: str = typer.Argument(..., help="Run identifier."),
    request_id: str = typer.Argument(..., help="Approval request identifier."),
    actor: str = typer.Option(..., "--actor", help="Human approver actor id."),
    reason: str = typer.Option("", "--reason", help="Optional revoke reason."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    try:
        request = revoke_request(
            project_root / ".sac",
            run_id,
            request_id,
            decision_actor=actor,
            decision_note=reason,
        )
    except RequestAlreadyConsumedError:
        typer.echo("Approval request cannot be revoked.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"request_id": request.request_id, "status": request.status}))
    raise typer.Exit(code=0)
