"""Enterprise CLI commands."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.approvals.cli_render import render_pending_requests
from safecode.enterprise.rbac.models import resolve_subject
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestNotFoundError,
    RequestAlreadyConsumedError,
    UnsupportedWorkflowTaskError,
    WorkflowError,
    WorkflowInterrupted,
)
from safecode.enterprise.workflow.orchestrator import (
    LocalOrchestrator,
    build_initial_state,
    ensure_workflow_task_executable,
)
from safecode.enterprise.workflow.types import TaskType
from safecode.enterprise.trace.timeline import build_timeline, serialize_timeline
from safecode.enterprise.trace.render_markdown import render_markdown
from safecode.enterprise.trace.redaction import DebugTraceNotAllowed, resolve_export_profile
from safecode.enterprise.policy.resolver import resolve_policy
from safecode.enterprise.workflow.exceptions import CheckpointCorruptedError, InvalidRunIdError
from safecode.enterprise.eval.dashboard import render_dashboard, write_dashboard
from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.ratchet import baseline_path_for_suite, check_ratchet, write_baseline
from safecode.enterprise.eval.runner import run_suite
from safecode.enterprise.evidence.export import verify_export_bundle
from safecode.enterprise.client.api_client import (
    EnterpriseApiClient,
    ServerModeError,
    load_bearer_token,
    reject_raw_token_argv,
)

RAG_MAX_CITATIONS = 8
_EVAL_CASES_ROOT = Path("tests/enterprise/eval/cases")
_EVAL_BASELINES_ROOT = Path("tests/enterprise/eval/baselines")
_EVAL_MANIFEST = Path("examples/enterprise/knowledge_sources.yaml")
_IMPLEMENTED_EVAL_SUITES = (
    "smoke",
    "retrieval",
    "prompt_injection",
    "tool_classification",
    "pr_review",
    "remediation",
)

enterprise_app = typer.Typer(help="Enterprise security workflow commands.")
workflow_app = typer.Typer(help="Enterprise workflow orchestration.")
approval_app = typer.Typer(help="Enterprise approval inbox.")
trace_app = typer.Typer(help="Enterprise trace export and dashboard.")
eval_app = typer.Typer(help="Enterprise evaluation suites.")
evidence_app = typer.Typer(help="Enterprise compliance evidence export.")
enterprise_app.add_typer(workflow_app, name="workflow")
enterprise_app.add_typer(approval_app, name="approval")
enterprise_app.add_typer(trace_app, name="trace")
enterprise_app.add_typer(eval_app, name="eval")
enterprise_app.add_typer(evidence_app, name="evidence")


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
    actor: Optional[str] = typer.Option(None, "--actor", help="Actor identifier."),
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
    as_role: Optional[str] = typer.Option(
        None, "--as-role", help="Override role when org policy allows."
    ),
    config_root: Optional[Path] = typer.Option(
        None, "--config-root", help="Enterprise config root."
    ),
    server_url: Optional[str] = typer.Option(
        None, "--server-url", help="Team Server base URL for server mode."
    ),
    token_stdin: bool = typer.Option(
        False, "--token-stdin", help="Read bearer token from stdin for server mode."
    ),
) -> None:
    """Start an enterprise workflow run locally or via the Team Server API."""
    project_root = (root or Path.cwd()).resolve()
    sac_root = project_root / ".sac"
    try:
        task_type = TaskType(task)
    except ValueError as exc:
        typer.echo("Unsupported task type.", err=True)
        raise typer.Exit(code=1) from exc
    if server_url:
        if actor is not None:
            typer.echo("server mode rejects --actor", err=True)
            raise typer.Exit(code=1)
        try:
            reject_raw_token_argv(sys.argv[1:])
            token = load_bearer_token(token_stdin=token_stdin)
        except ServerModeError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        idempotency_key = hashlib.sha256(
            f"{tenant}:{task}:{input_path.resolve()}".encode("utf-8")
        ).hexdigest()[:32]
        try:
            payload = EnterpriseApiClient(
                base_url=server_url,
                tenant_id=tenant,
                bearer_token=token,
            ).start_run(
                task_type=task_type.value,
                input_ref=str(input_path),
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            typer.echo("Unable to start workflow via Team Server.", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps({"run_id": payload["run_id"], "status": payload["status"]}))
        raise typer.Exit(code=0)
    try:
        resolve_subject(actor or "user:local", config_root=config_root, as_role=as_role)
    except PermissionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    try:
        ensure_workflow_task_executable(task_type)
    except UnsupportedWorkflowTaskError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    state = build_initial_state(
        task_type=task_type,
        input_ref=str(input_path),
        actor_id=actor or "user:local",
        repo_root=project_root,
        tenant_id=tenant,
    )
    run_id = state.run_id
    orchestrator = LocalOrchestrator(sac_root)
    try:
        final = asyncio.run(orchestrator.run(state))
    except WorkflowInterrupted:
        typer.echo(json.dumps({"run_id": run_id, "status": "awaiting_approval"}))
        raise typer.Exit(code=3)
    except WorkflowError as exc:
        typer.echo(str(exc) or "Workflow failed.", err=True)
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
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
) -> None:
    """Remove stale workflow run directories under .sac/enterprise/runs."""
    if not older_than.endswith("d"):
        typer.echo("Only day-based retention like 7d is supported.", err=True)
        raise typer.Exit(code=1)
    days = int(older_than[:-1])
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    removed = backend.runs.gc_runs(tenant_id=tenant, older_than_days=days)
    typer.echo(json.dumps({"removed": removed}))
    raise typer.Exit(code=0)


@approval_app.command("list")
def approval_list(
    run_id: str = typer.Argument(..., help="Run identifier."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
    pending: bool = typer.Option(False, "--pending", help="Show only pending requests."),
    markdown: bool = typer.Option(False, "--markdown", help="Render pending requests as Markdown."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    requests = (
        backend.approvals.list_pending_requests(tenant_id=tenant, run_id=run_id)
        if pending
        else backend.approvals.list_requests(tenant_id=tenant, run_id=run_id)
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
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        request = backend.approvals.load_request(
            tenant_id=tenant, run_id=run_id, request_id=request_id
        )
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
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        request = backend.approvals.decide_request(
            tenant_id=tenant,
            run_id=run_id,
            request_id=request_id,
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
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        request = backend.approvals.decide_request(
            tenant_id=tenant,
            run_id=run_id,
            request_id=request_id,
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
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        request = backend.approvals.request_evidence(
            tenant_id=tenant,
            run_id=run_id,
            request_id=request_id,
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
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
) -> None:
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        request = backend.approvals.revoke_request(
            tenant_id=tenant,
            run_id=run_id,
            request_id=request_id,
            decision_actor=actor,
            decision_note=reason,
        )
    except RequestAlreadyConsumedError:
        typer.echo("Approval request cannot be revoked.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"request_id": request.request_id, "status": request.status}))
    raise typer.Exit(code=0)


@trace_app.command("export")
def trace_export(
    run_id: str = typer.Argument(..., help="Run identifier."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Write timeline JSON."),
    profile: str = typer.Option("strict", "--profile", help="Trace export profile."),
    config_root: Optional[Path] = typer.Option(
        None, "--config-root", help="Enterprise config root."
    ),
) -> None:
    """Export a canonical run timeline JSON artifact."""
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        backend.runs.load_checkpoint(tenant_id=tenant, run_id=run_id)
    except (InvalidRunIdError, CheckpointCorruptedError, FileNotFoundError):
        typer.echo("Run not found.", err=True)
        raise typer.Exit(code=1)
    try:
        resolve_export_profile(resolve_policy(project_root, config_root=config_root), requested=profile)
    except DebugTraceNotAllowed as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        path = backend.trace.write_timeline(tenant_id=tenant, run_id=run_id)
        typer.echo(path.read_text(encoding="utf-8"))
    else:
        typer.echo(serialize_timeline(build_timeline(backend.sac_root, run_id)))
    raise typer.Exit(code=0)


@trace_app.command("show")
def trace_show(
    run_id: str = typer.Argument(..., help="Run identifier."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    tenant: str = typer.Option("local", "--tenant", help="Tenant identifier."),
    out: Optional[Path] = typer.Option(None, "--out", help="Optional output Markdown path."),
    profile: str = typer.Option("strict", "--profile", help="Trace export profile."),
    config_root: Optional[Path] = typer.Option(
        None, "--config-root", help="Enterprise config root."
    ),
) -> None:
    """Render a Markdown dashboard for a workflow run."""
    project_root = (root or Path.cwd()).resolve()
    backend = LocalBackend(project_root / ".sac")
    try:
        backend.runs.load_checkpoint(tenant_id=tenant, run_id=run_id)
    except (InvalidRunIdError, CheckpointCorruptedError, FileNotFoundError):
        typer.echo("Run not found.", err=True)
        raise typer.Exit(code=1)
    try:
        resolve_export_profile(resolve_policy(project_root, config_root=config_root), requested=profile)
    except DebugTraceNotAllowed as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    markdown = render_markdown(build_timeline(backend.sac_root, run_id))
    if out is not None:
        out.write_text(markdown, encoding="utf-8")
    typer.echo(markdown)
    raise typer.Exit(code=0)


def _project_root(root: Path | None) -> Path:
    return (root or Path.cwd()).resolve()


def _resolve_under(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (project_root / path).resolve()


def _git_head_short(project_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


@eval_app.command("run")
def eval_run(
    suite: str = typer.Option("all", "--suite", help="Suite name or all."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    cases_root: Path = typer.Option(
        _EVAL_CASES_ROOT, "--cases-root", help="Eval cases root."
    ),
    baselines_root: Path = typer.Option(
        _EVAL_BASELINES_ROOT, "--baselines-root", help="Baseline JSON root."
    ),
    manifest: Path = typer.Option(
        _EVAL_MANIFEST, "--manifest", help="Knowledge manifest for retrieval."
    ),
    update_baseline: bool = typer.Option(
        False, "--update-baseline", help="Rewrite suite baseline files."
    ),
) -> None:
    """Run enterprise evaluation suites and write results plus dashboard."""
    project_root = _project_root(root)
    sac_root = project_root / ".sac"
    resolved_cases = _resolve_under(project_root, cases_root)
    resolved_baselines = _resolve_under(project_root, baselines_root)
    resolved_manifest = _resolve_under(project_root, manifest)

    if suite == "all":
        suites = list(_IMPLEMENTED_EVAL_SUITES)
    elif suite in _IMPLEMENTED_EVAL_SUITES:
        suites = [suite]
    else:
        typer.echo(f"Unsupported suite: {suite}", err=True)
        raise typer.Exit(code=1)

    all_results = []
    ratchet_failures: list[str] = []
    recorded_at = datetime.now(timezone.utc).date().isoformat()
    commit = _git_head_short(project_root)

    for suite_name in suites:
        cases = discover_cases(resolved_cases, suite=suite_name)
        if not cases:
            continue
        manifest_path = resolved_manifest if suite_name == "retrieval" else None
        results = run_suite(cases, project_root=project_root, manifest_path=manifest_path)
        all_results.extend(results)
        baseline_path = baseline_path_for_suite(resolved_baselines, suite_name)
        if baseline_path is None:
            continue
        if update_baseline:
            write_baseline(results, baseline_path, commit=commit, recorded_at=recorded_at)
        else:
            ratchet_failures.extend(check_ratchet(results, baseline_path))

    if ratchet_failures and not update_baseline:
        typer.echo(json.dumps({"passed": False, "failures": ratchet_failures}))
        raise typer.Exit(code=1)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backend = LocalBackend(sac_root)
    results_path = backend.eval_results.write_results(
        tenant_id="local", run_id=run_id, results=all_results
    )
    dashboard_path = write_dashboard(sac_root, render_dashboard(all_results))
    passed = all(item.passed for item in all_results)
    typer.echo(
        json.dumps(
            {
                "passed": passed,
                "dashboard": str(dashboard_path),
                "results": str(results_path),
                "run_id": run_id,
            }
        )
    )
    raise typer.Exit(code=0 if passed else 1)


@eval_app.command("dashboard")
def eval_dashboard(
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
) -> None:
    """Print the latest enterprise evaluation dashboard Markdown."""
    path = _project_root(root) / ".sac" / "enterprise" / "eval" / "latest.md"
    if not path.is_file():
        typer.echo("Eval dashboard not found. Run eval first.", err=True)
        raise typer.Exit(code=1)
    typer.echo(path.read_text(encoding="utf-8"))
    raise typer.Exit(code=0)


@evidence_app.command("export")
def evidence_export(
    run_id: str = typer.Option(..., "--run", help="Workflow run identifier."),
    tenant: str = typer.Option("local", "--tenant", help="Expected workflow tenant."),
    root: Path = typer.Option(None, "--root", help="Project root (defaults to cwd)."),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Verify bundle after export."),
) -> None:
    """Export a compliance evidence zip for a completed workflow run."""
    project_root = _project_root(root)
    backend = LocalBackend(project_root / ".sac")
    try:
        bundle_path = backend.evidence.export_run_evidence(tenant_id=tenant, run_id=run_id)
    except Exception as exc:
        typer.echo(f"Evidence export failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    ok = True
    message = "skipped"
    if verify:
        ok, message = verify_export_bundle(bundle_path)
    typer.echo(
        json.dumps(
            {
                "bundle": str(bundle_path),
                "verified": ok,
                "verification_message": message,
            }
        )
    )
    raise typer.Exit(code=0 if ok else 1)
