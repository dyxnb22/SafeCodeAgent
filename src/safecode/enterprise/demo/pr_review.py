"""Offline PR security review portfolio demo."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from safecode.enterprise.approvals.store import approvals_dir, decide_request
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

DEMO_NAME = "pr-review"
DEMO_RUN_ID = "run-demoprreview"
FIXTURE_REF = "examples/enterprise/fixtures/pr_sql_injection"
STABLE_AUDIT_CHAIN_HEAD = "generated"


def reset_demo_run_state(workspace_root: Path, *, run_id: str = DEMO_RUN_ID) -> None:
    """Remove disposable demo run state so offline demos can be repeated."""
    sac_root = workspace_root.resolve() / ".sac"
    run_dir = sac_root / "enterprise" / "runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    approval_dir = approvals_dir(sac_root, run_id)
    if approval_dir.exists():
        shutil.rmtree(approval_dir)


def prepare_demo_workspace(project_root: Path, workspace_root: Path) -> None:
    """Copy enterprise fixtures into an isolated demo workspace."""
    src = project_root.resolve() / "examples" / "enterprise"
    dst = workspace_root.resolve() / "examples" / "enterprise"
    if not src.is_dir():
        raise FileNotFoundError(
            f"Missing enterprise fixtures under {src}; run from the repository root."
        )
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def run_pr_review_offline_demo(
    project_root: Path,
    *,
    workspace_root: Path | None = None,
    keep_runs: bool = False,
    show_run_metadata: bool = False,
) -> str:
    """Run the offline PR review demo and return a human-readable transcript."""
    root = project_root.resolve()
    owned_workspace: Path | None = None
    if workspace_root is not None:
        workspace = workspace_root.resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        prepare_demo_workspace(root, workspace)
        cleanup_workspace = False
    else:
        owned_workspace = Path(tempfile.mkdtemp(prefix="sac-demo-"))
        workspace = owned_workspace
        prepare_demo_workspace(root, workspace)
        cleanup_workspace = not keep_runs

    try:
        return _run_pr_review_in_workspace(
            workspace,
            show_run_metadata=show_run_metadata,
        )
    finally:
        if cleanup_workspace and owned_workspace is not None:
            shutil.rmtree(owned_workspace, ignore_errors=True)


def _run_pr_review_in_workspace(
    workspace_root: Path,
    *,
    show_run_metadata: bool,
) -> str:
    reset_demo_run_state(workspace_root)
    sac_root = workspace_root / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=FIXTURE_REF,
        actor_id="user:demo",
        repo_root=workspace_root,
        run_id=DEMO_RUN_ID,
    )
    try:
        asyncio.run(orchestrator.run(state))
    except WorkflowInterrupted:
        pass
    decide_request(
        sac_root,
        DEMO_RUN_ID,
        f"approval-{DEMO_RUN_ID}",
        decision="rejected",
        decision_actor="user:reviewer",
        decision_note="offline demo refuses gated write",
    )
    final = asyncio.run(orchestrator.resume(DEMO_RUN_ID))
    checkpoint = load_checkpoint(sac_root, DEMO_RUN_ID)
    return _format_transcript(
        workspace_root,
        final,
        checkpoint,
        show_run_metadata=show_run_metadata,
    )


def _format_transcript(
    workspace_root: Path,
    final_state,
    checkpoint,
    *,
    show_run_metadata: bool,
) -> str:
    lines = [
        "=== SafeCodeAgent Enterprise Demo ===",
        f"demo name: {DEMO_NAME}",
        "mode: offline",
        "",
        "--- classification ---",
        f"task_type: {final_state.task_type.value}",
        f"input_kind: {final_state.request.input_kind}",
    ]
    classify = final_state.node_outputs.get("classify_request")
    if classify is not None:
        lines.append(f"classification: {classify.summary}")
    lines.extend(
        [
            "",
            "--- evidence ---",
            f"fixture: {FIXTURE_REF}/pr.json",
        ]
    )
    if final_state.pull_request_evidence is not None:
        evidence = final_state.pull_request_evidence
        lines.append(f"evidence_source: pr_fixture ({evidence.title})")
    lines.append("")
    lines.append("--- citations ---")
    if final_state.citations:
        for citation in final_state.citations[:4]:
            lines.append(
                f"citation_id: {citation.citation_id} "
                f"(source_id={citation.source_id})"
            )
    else:
        lines.append("citation_id: none")
    lines.extend(["", "--- workflow timeline ---"])
    for node_name in WORKFLOW_NODE_ORDER:
        output = final_state.node_outputs.get(node_name)
        summary = output.summary if output is not None else "skipped"
        lines.append(f"node: {node_name} | {summary}")
    lines.extend(
        [
            "",
            "--- approval gate ---",
            f"workflow_status: {final_state.status.value}",
            "approval-gated action: refused",
            "gated_action: file_write",
            "decision: rejected",
        ]
    )
    if final_state.status != WorkflowStatus.rejected:
        lines.append("note: approval gate did not terminate as rejected")
    lines.extend(["", "--- audit chain ---"])
    chain = EnterpriseAuditChain(workspace_root)
    ok, message = chain.verify_integrity()
    lines.append(f"audit_integrity: {'verified' if ok else 'failed'}")
    lines.append(f"audit_summary: {message}")
    lines.append(
        _audit_chain_head_line(chain, show_run_metadata=show_run_metadata)
    )
    lines.append(f"completed_nodes: {len(checkpoint.completed_nodes)}")
    return "\n".join(lines) + "\n"


def _audit_chain_head_line(
    chain: EnterpriseAuditChain,
    *,
    show_run_metadata: bool,
) -> str:
    if not show_run_metadata:
        return f"audit_chain_head: {STABLE_AUDIT_CHAIN_HEAD}"
    events = chain.iter_events()
    run_events = [
        event
        for event in events
        if event.metadata.get("run_id") == DEMO_RUN_ID
        or event.metadata.get("task_id") == DEMO_RUN_ID
    ]
    if run_events:
        return f"audit_chain_head: {run_events[-1].event_hash}"
    if events:
        return f"audit_chain_head: {events[-1].event_hash}"
    return "audit_chain_head: none"
