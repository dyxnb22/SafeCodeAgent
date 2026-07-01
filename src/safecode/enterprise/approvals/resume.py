"""Enqueue durable workflow resume jobs after approval decisions (R8).

中文模块说明：审批决定后，将可恢复的 workflow resume 命令入队给 worker。
- 架构位置：连接 Approval API 与 Workflow 平面。
- 安全不变量：仅 approved 且 grant 仍有效时 resume；幂等键防止重复执行。
- 学习路径：对照 ``worker/commands.py`` 的 resume 路径与 ``test_approval_interrupt.py``。
"""

from __future__ import annotations

from safecode.enterprise.api.idempotency import approval_resume_idempotency_key
from safecode.enterprise.approvals.store import ApprovalRequest
from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.worker.commands import command_queue_for
from safecode.enterprise.worker.queue import CommandQueue, ensure_command_enqueued


def ensure_approval_resume_enqueued(
    backend: object,
    *,
    tenant_id: str,
    request: ApprovalRequest,
    decision: str,
) -> None:
    """Record and enqueue exactly one resume job for a terminal approval decision."""
    if decision not in {"approved", "rejected", "revoked"}:
        return
    tenant = validate_tenant_id(tenant_id)
    queue = command_queue_for(backend)
    resume_key = approval_resume_idempotency_key(
        tenant_id=tenant,
        approval_id=request.request_id,
        decision=decision,
    )
    ensure_command_enqueued(
        queue,
        tenant_id=tenant,
        idempotency_key=resume_key,
        command="resume",
        run_id=request.run_id,
        payload={
            "approval_id": request.request_id,
            "decision": decision,
        },
    )


def command_queue_for_resume(backend: object) -> CommandQueue:
    return command_queue_for(backend)
