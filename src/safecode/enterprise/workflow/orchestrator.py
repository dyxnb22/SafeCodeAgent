"""Local workflow orchestrator."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from safecode.enterprise.approvals.store import list_requests
from safecode.enterprise.workflow.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    RunCheckpoint,
    load_checkpoint,
    save_checkpoint,
)
from safecode.enterprise.workflow.exceptions import (
    InvalidWorkflowRuntimeError,
    LangGraphUnavailableError,
    UnknownTaskTypeError,
    WorkflowInterrupted,
)
from safecode.enterprise.workflow.ids import generate_run_id, validate_run_id
from safecode.enterprise.workflow.nodes.registry import NODE_RUNNERS, WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.patch import apply_patch
from safecode.enterprise.workflow.state import (
    EnterpriseRunState,
    RBACSubject,
    RepoContext,
    RunRequest,
    RunCosts,
)
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

SUPPORTED_TASK_TYPES = frozenset(TaskType)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_initial_state(
    *,
    task_type: TaskType,
    input_ref: str,
    actor_id: str,
    repo_root: Path,
    run_id: str | None = None,
    extra: dict[str, str] | None = None,
) -> EnterpriseRunState:
    if task_type not in SUPPORTED_TASK_TYPES:
        raise UnknownTaskTypeError(f"unsupported task type: {task_type!r}")
    run = validate_run_id(run_id or generate_run_id())
    now = utc_now_iso()
    return EnterpriseRunState(
        run_id=run,
        tenant_id="local",
        task_type=task_type,
        status=WorkflowStatus.pending,
        actor_id=actor_id,
        subject=RBACSubject(actor_id=actor_id, tenant_id="local"),
        policy_snapshot_id="snapshot-local",
        request=RunRequest(
            task_type=task_type,
            input_kind="pr_fixture",
            input_ref=input_ref,
            actor_id=actor_id,
            extra=dict(extra or {}),
        ),
        repo=RepoContext(repo_root=str(repo_root.resolve())),
        costs=RunCosts(started_at=now),
        created_at=now,
        updated_at=now,
    )


def workflow_runtime() -> str:
    runtime = os.environ.get("WORKFLOW_RUNTIME", "local").strip().lower()
    if runtime not in {"local", "langgraph"}:
        raise InvalidWorkflowRuntimeError(f"unsupported WORKFLOW_RUNTIME: {runtime!r}")
    return runtime


class LocalOrchestrator:
    """Runs workflow nodes in declared order with checkpoint persistence."""

    def __init__(self, sac_root: Path, *, runtime: str | None = None) -> None:
        self.sac_root = sac_root
        self.runtime = runtime or workflow_runtime()

    async def run(self, state: EnterpriseRunState) -> EnterpriseRunState:
        if self.runtime == "langgraph":
            from safecode.enterprise.workflow.graph import run_langgraph_workflow

            return await run_langgraph_workflow(self.sac_root, state)
        return await self._run_local(state, completed_nodes=[])

    async def resume(self, run_id: str) -> EnterpriseRunState:
        checkpoint = load_checkpoint(self.sac_root, run_id)
        state = checkpoint.state
        if state.status == WorkflowStatus.awaiting_approval:
            requests = list_requests(self.sac_root, run_id)
            if any(item.status == "rejected" for item in requests):
                rejected = state.model_copy(
                    update={
                        "status": WorkflowStatus.rejected,
                        "awaiting_human_approval": False,
                        "updated_at": utc_now_iso(),
                    }
                )
                save_checkpoint(
                    self.sac_root,
                    RunCheckpoint(
                        schema_version=CHECKPOINT_SCHEMA_VERSION,
                        run_id=rejected.run_id,
                        completed_nodes=list(checkpoint.completed_nodes),
                        next_node=None,
                        state=rejected,
                    ),
                )
                return rejected
            if not any(item.status == "approved" for item in requests):
                raise WorkflowInterrupted(f"awaiting approval for run {run_id}")
            state = state.model_copy(
                update={
                    "awaiting_human_approval": False,
                    "status": WorkflowStatus.running,
                    "updated_at": utc_now_iso(),
                }
            )
        if self.runtime == "langgraph":
            from safecode.enterprise.workflow.graph import resume_langgraph_workflow

            return await resume_langgraph_workflow(self.sac_root, checkpoint)
        return await self._run_local(state, completed_nodes=list(checkpoint.completed_nodes))

    async def _run_local(
        self,
        state: EnterpriseRunState,
        *,
        completed_nodes: list[str],
    ) -> EnterpriseRunState:
        current = state
        start_index = len(completed_nodes)
        for node_name in WORKFLOW_NODE_ORDER[start_index:]:
            if node_name in completed_nodes:
                continue
            runner = NODE_RUNNERS[node_name]
            patch = await runner(current)
            current = apply_patch(current, patch)
            completed_nodes = [*completed_nodes, node_name]
            next_node = (
                WORKFLOW_NODE_ORDER[len(completed_nodes)]
                if len(completed_nodes) < len(WORKFLOW_NODE_ORDER)
                else None
            )
            save_checkpoint(
                self.sac_root,
                RunCheckpoint(
                    schema_version=CHECKPOINT_SCHEMA_VERSION,
                    run_id=current.run_id,
                    completed_nodes=completed_nodes,
                    next_node=next_node,
                    state=current,
                ),
            )
            if (
                node_name == "approval_gate"
                and current.awaiting_human_approval
                and current.risk_tier is not None
                and current.risk_tier.value in {"high", "critical"}
            ):
                from safecode.enterprise.approvals.store import Action, ApprovalRequest
                from safecode.enterprise.workflow.interrupt import pause_for_approval

                request = ApprovalRequest(
                    request_id=f"approval-{current.run_id}",
                    run_id=current.run_id,
                    action=Action.file_write,
                    risk_tier=current.risk_tier,
                    requested_by_node=node_name,
                    requesting_actor=current.actor_id,
                    policy_snapshot_id=current.policy_snapshot_id,
                    created_at=current.updated_at,
                    preview="High-risk workflow action requires approval.",
                )
                pause_for_approval(self.sac_root, current, request)
            if current.status == WorkflowStatus.awaiting_approval:
                raise WorkflowInterrupted(f"awaiting approval at node {node_name}")
        return current
