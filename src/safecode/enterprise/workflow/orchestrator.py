"""本地工作流编排器（Local Orchestrator）。

编排器按 ``WORKFLOW_NODE_ORDER`` 声明的节点顺序依次执行，每步：
1. 调用节点 runner 产出 ``NodePatch``
2. ``apply_patch`` 合并到 ``EnterpriseRunState``
3. 持久化 ``RunCheckpoint``（含 ``completed_nodes`` 与 ``next_node``）
4. 在 ``approval_gate`` 处若需人审则暂停并抛出 ``WorkflowInterrupted``

恢复（``resume``）从检查点加载状态，校验审批结果后从 ``completed_nodes``
长度对应的索引继续执行。``WORKFLOW_RUNTIME=langgraph`` 时委托给 LangGraph 适配层。

潜在问题：
- LangGraph 路径与本地路径在条件分支（缺证据、高风险、校验失败）上行为不完全一致
- ``resume`` 在 langgraph 模式下最终仍回落到本地编排器（见 graph.resume_langgraph_workflow）
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from safecode.enterprise.approvals.binding import workflow_approval_binding
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.policy.resolver import resolve_policy
from safecode.enterprise.worker.status import is_terminal
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import TraceSession
from safecode.enterprise.workflow.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    RunCheckpoint,
)
from safecode.enterprise.workflow.exceptions import (
    InvalidWorkflowRuntimeError,
    LangGraphUnavailableError,
    TenantContextRequiredError,
    UnknownTaskTypeError,
    UnsupportedWorkflowTaskError,
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
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus

SUPPORTED_TASK_TYPES = frozenset(TaskType)

COMPLIANCE_EXPORT_UNSUPPORTED_MSG = (
    "compliance_export workflow is not implemented; "
    "use `sac enterprise evidence export --run <run_id>` for standalone evidence export"
)


def ensure_workflow_task_executable(task_type: TaskType) -> None:
    if task_type is TaskType.compliance_export:
        raise UnsupportedWorkflowTaskError(COMPLIANCE_EXPORT_UNSUPPORTED_MSG)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_initial_state(
    *,
    task_type: TaskType,
    input_ref: str,
    actor_id: str,
    repo_root: Path,
    run_id: str | None = None,
    tenant_id: str = "local",
    extra: dict[str, str] | None = None,
) -> EnterpriseRunState:
    """构造工作流初始状态：解析策略快照、设置 input_kind 与 RBAC 主体。"""
    if task_type not in SUPPORTED_TASK_TYPES:
        raise UnknownTaskTypeError(f"unsupported task type: {task_type!r}")
    ensure_workflow_task_executable(task_type)
    run = validate_run_id(run_id or generate_run_id())
    now = utc_now_iso()
    tid = (tenant_id or "local").strip() or "local"
    input_kind = "finding_fixture" if task_type == TaskType.remediation else "pr_fixture"
    if task_type == TaskType.secure_planning:
        input_kind = "ticket"
    snapshot = resolve_policy(repo_root, tenant_id=tid)
    return EnterpriseRunState(
        run_id=run,
        tenant_id=tid,
        task_type=task_type,
        status=WorkflowStatus.pending,
        actor_id=actor_id,
        subject=RBACSubject(actor_id=actor_id, tenant_id=tid),
        policy_snapshot_id=snapshot.snapshot_id,
        request=RunRequest(
            task_type=task_type,
            input_kind=input_kind,
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
    """按声明顺序执行工作流节点，并在每步后持久化检查点。

    支持 ``local``（线性遍历）与 ``langgraph``（条件图）两种运行时。
    """

    def __init__(
        self,
        sac_root: Path,
        *,
        runtime: str | None = None,
        backend: LocalBackend | None = None,
    ) -> None:
        self.sac_root = sac_root
        self.backend = backend or LocalBackend(sac_root)
        self.runtime = runtime or workflow_runtime()

    async def run(self, state: EnterpriseRunState) -> EnterpriseRunState:
        if self.runtime == "langgraph":
            from safecode.enterprise.workflow.graph import run_langgraph_workflow

            return await run_langgraph_workflow(self.backend, state)
        return await self._run_local(state, completed_nodes=[])

    async def resume(
        self,
        run_id: str,
        *,
        tenant_id: str | None = None,
    ) -> EnterpriseRunState:
        """从检查点恢复执行。

        若状态为 ``awaiting_approval``，先加载审批请求并校验绑定（action/target/
        policy_snapshot_id），通过后将状态置为 ``running`` 再继续节点循环。
        调用方必须显式传入 ``tenant_id`` 以防跨租户恢复。
        """
        if tenant_id is None:
            raise TenantContextRequiredError(
                "resume requires tenant_id; callers must resolve tenant context before resuming"
            )
        checkpoint = self.backend.runs.load_checkpoint(
            tenant_id=tenant_id, run_id=run_id
        )
        state = checkpoint.state
        if is_terminal(state.status):
            return state
        if state.status == WorkflowStatus.awaiting_approval:
            request_id = f"approval-{run_id}"
            request = self.backend.approvals.load_request(
                tenant_id=state.tenant_id,
                run_id=run_id,
                request_id=request_id,
            )
            if request.status == "rejected":
                rejected = state.model_copy(
                    update={
                        "status": WorkflowStatus.rejected,
                        "awaiting_human_approval": False,
                        "updated_at": utc_now_iso(),
                    }
                )
                self.backend.runs.save_checkpoint(
                    tenant_id=rejected.tenant_id,
                    checkpoint=RunCheckpoint(
                        schema_version=CHECKPOINT_SCHEMA_VERSION,
                        run_id=rejected.run_id,
                        completed_nodes=list(checkpoint.completed_nodes),
                        next_node=None,
                        state=rejected,
                    ),
                )
                return rejected
            if request.status != "approved":
                raise WorkflowInterrupted(f"awaiting approval for run {run_id}")
            action, target = workflow_approval_binding(state)
            self.backend.approvals.validate_approved_request(
                tenant_id=state.tenant_id,
                run_id=run_id,
                request_id=request_id,
                action=action,
                policy_snapshot_id=state.policy_snapshot_id,
                target=target,
            )
            state = state.model_copy(
                update={
                    "awaiting_human_approval": False,
                    "status": WorkflowStatus.running,
                    "updated_at": utc_now_iso(),
                }
            )
        if self.runtime == "langgraph":
            from safecode.enterprise.workflow.graph import resume_langgraph_workflow

            return await resume_langgraph_workflow(self.backend, checkpoint)
        return await self._run_local(state, completed_nodes=list(checkpoint.completed_nodes))

    async def _run_local(
        self,
        state: EnterpriseRunState,
        *,
        completed_nodes: list[str],
    ) -> EnterpriseRunState:
        """本地线性执行：从 ``completed_nodes`` 长度处切片 ``WORKFLOW_NODE_ORDER``。"""
        current = state
        try:
            ensure_workflow_task_executable(current.task_type)
        except UnsupportedWorkflowTaskError:
            failed = current.model_copy(
                update={
                    "status": WorkflowStatus.failed,
                    "updated_at": utc_now_iso(),
                }
            )
            self.backend.runs.save_checkpoint(
                tenant_id=failed.tenant_id,
                checkpoint=RunCheckpoint(
                    schema_version=CHECKPOINT_SCHEMA_VERSION,
                    run_id=failed.run_id,
                    completed_nodes=list(completed_nodes),
                    next_node=None,
                    state=failed,
                ),
            )
            return failed
        trace = TraceSession(self.sac_root, current)
        start_index = len(completed_nodes)
        if start_index == 0:
            trace.emit(
                TraceEventType.workflow_start,
                node_id="orchestrator",
                payload={"task_type": current.task_type.value},
            )
        # 按固定顺序遍历节点；恢复时跳过已完成节点
        for node_name in WORKFLOW_NODE_ORDER[start_index:]:
            if node_name in completed_nodes:
                continue
            trace.emit(TraceEventType.node_start, node_id=node_name)
            runner = NODE_RUNNERS[node_name]
            patch = await runner(current)
            current = apply_patch(current, patch)
            node_output = current.node_outputs.get(node_name)
            trace.emit(
                TraceEventType.node_end,
                node_id=node_name,
                payload={
                    "summary": node_output.summary if node_output else patch.node_name,
                    "status": patch.status,
                },
                cost=patch.cost,
                duration_ms=patch.duration_ms,
            )
            completed_nodes = [*completed_nodes, node_name]
            next_node = (
                WORKFLOW_NODE_ORDER[len(completed_nodes)]
                if len(completed_nodes) < len(WORKFLOW_NODE_ORDER)
                else None
            )
            # 每节点结束后写检查点，供 worker 崩溃恢复与 API 查询进度
            self.backend.runs.save_checkpoint(
                tenant_id=current.tenant_id,
                checkpoint=RunCheckpoint(
                    schema_version=CHECKPOINT_SCHEMA_VERSION,
                    run_id=current.run_id,
                    completed_nodes=completed_nodes,
                    next_node=next_node,
                    state=current,
                ),
            )
            # 审批门：高风险动作暂停工作流，等待人工批准后再 resume
            if node_name == "approval_gate" and current.awaiting_human_approval:
                from safecode.enterprise.approvals.store import ApprovalRequest
                from safecode.enterprise.workflow.interrupt import pause_for_approval

                action, target = workflow_approval_binding(current)
                request = ApprovalRequest(
                    request_id=f"approval-{current.run_id}",
                    run_id=current.run_id,
                    tenant_id=current.tenant_id,
                    action=action,
                    risk_tier=current.risk_tier or RiskTier.low,
                    requested_by_node=node_name,
                    requesting_actor=current.actor_id,
                    target=target,
                    policy_snapshot_id=current.policy_snapshot_id,
                    created_at=current.updated_at,
                    preview="High-risk workflow action requires approval.",
                )
                pause_for_approval(self.backend, current, request)
            if current.status == WorkflowStatus.awaiting_approval:
                # 中断异常由 worker 捕获，任务保持 pending 直至审批完成
                raise WorkflowInterrupted(f"awaiting approval at node {node_name}")
        trace.emit(
            TraceEventType.workflow_end,
            node_id="orchestrator",
            payload={"status": current.status.value},
        )
        return current
