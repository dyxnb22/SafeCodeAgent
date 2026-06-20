"""基于文件系统的持久化适配器，实现 v2.1.2 仓储协议。

架构概览（前 80 行涉及的核心结构）：
- ``LocalRunStore``：工作流检查点（``state.json`` + completed_nodes），租户隔离校验
- ``LocalApprovalStore``：审批请求与 grant 的读写、消费与撤销
- ``LocalBackend``（文件后部）：聚合 runs/approvals/audit/trace/evidence/eval/
  commands/leases/webhooks 等子存储，作为 API 与 Worker 的统一注入点

数据根目录为 ``sac_root``（通常 ``SAC_ENTERPRISE_ARTIFACTS_ROOT``），
各租户/run 按目录分层存放。所有跨租户访问经 ``assert_tenant_match`` 拦截。

潜在问题：
- ``load_checkpoint`` 先按 run_id 加载再校验 tenant，run_id 全局唯一假设需保持
- ``purge_run`` 在目录存在但无 state.json 时可能跳过租户校验直接 rmtree
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from safecode.audit.models import AuditEvent
from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
    consume_approved_request,
    consume_grant,
    decide_request,
    list_pending_requests,
    list_requests,
    load_grant,
    load_request,
    request_evidence,
    revoke_request,
    save_grant,
    save_request,
    validate_approved_request,
)
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.audit.tenant import filter_audit_events_by_tenant
from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.persistence.protocols import (
    ApprovalDecision,
    assert_tenant_match,
    validate_tenant_id,
)
from safecode.enterprise.persistence.webhook_store import LocalWebhookEventStore
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEvent, TraceEventType
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.trace.timeline import write_timeline
from safecode.enterprise.workflow.checkpoint import (
    RunCheckpoint,
    gc_runs,
    load_checkpoint,
    run_dir,
    save_checkpoint,
)
from safecode.enterprise.workflow.exceptions import CheckpointCorruptedError
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.ids import validate_run_id

if TYPE_CHECKING:
    from safecode.enterprise.worker.lease import LocalRunLeaseStore
    from safecode.enterprise.worker.queue import LocalCommandQueue


class LocalRunStore:
    """本地文件系统运行检查点存储。

    每个 run 对应 ``sac_root/enterprise/runs/<run_id>/`` 下的检查点文件；
    ``save_checkpoint`` / ``load_checkpoint`` 均强制 tenant_id 与状态内 tenant 一致。
    """

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None:
        """持久化检查点：含已完成节点列表、下一节点名与完整 EnterpriseRunState。"""
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="save_checkpoint")
        save_checkpoint(self.sac_root, checkpoint)

    def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint:
        """加载检查点供 worker resume 或 API 查询；租户不匹配则拒绝。"""
        tenant = validate_tenant_id(tenant_id)
        checkpoint = load_checkpoint(self.sac_root, run_id)
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="load_checkpoint")
        return checkpoint

    def resolve_run_tenant(self, *, run_id: str) -> str:
        validate_run_id(run_id)
        checkpoint = load_checkpoint(self.sac_root, run_id)
        return validate_tenant_id(checkpoint.state.tenant_id)

    def purge_run(self, *, tenant_id: str, run_id: str) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        directory = run_dir(self.sac_root, run_id)
        if not directory.is_dir():
            return
        if directory.is_dir() and (directory / "state.json").is_file():
            checkpoint = load_checkpoint(self.sac_root, run_id)
            assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="purge_run")
        shutil.rmtree(directory)

    def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]:
        validate_tenant_id(tenant_id)
        return gc_runs(self.sac_root, older_than_days=older_than_days)


class LocalApprovalStore:
    """本地审批与 grant 存储，与 workflow approval_gate 及 API approvals 路由共用。"""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def save_request(self, *, tenant_id: str, request: ApprovalRequest) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, request.tenant_id, operation="save_request")
        return save_request(self.sac_root, request)

    def load_request(
        self, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = load_request(self.sac_root, run_id, request_id)
        assert_tenant_match(tenant, request.tenant_id, operation="load_request")
        return request

    def list_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        return [item for item in list_requests(self.sac_root, run_id) if item.tenant_id == tenant]

    def list_pending_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for item in list_pending_requests(self.sac_root, run_id)
            if item.tenant_id == tenant
        ]

    def decide_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision: ApprovalDecision,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = decide_request(
            self.sac_root,
            run_id,
            request_id,
            decision=decision,
            decision_actor=decision_actor,
            decision_note=decision_note,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="decide_request")
        return request

    def request_evidence(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str,
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = request_evidence(
            self.sac_root,
            run_id,
            request_id,
            decision_actor=decision_actor,
            decision_note=decision_note,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="request_evidence")
        return request

    def revoke_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = revoke_request(
            self.sac_root,
            run_id,
            request_id,
            decision_actor=decision_actor,
            decision_note=decision_note,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="revoke_request")
        return request

    def save_grant(self, *, tenant_id: str, grant: Grant) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="save_grant")
        return save_grant(self.sac_root, grant)

    def load_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        grant = load_grant(self.sac_root, run_id, grant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="load_grant")
        return grant

    def consume_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        grant = consume_grant(self.sac_root, run_id, grant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="consume_grant")
        return grant

    def validate_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> tuple[ApprovalRequest, Grant]:
        tenant = validate_tenant_id(tenant_id)
        request, grant = validate_approved_request(
            self.sac_root,
            run_id,
            request_id,
            tenant_id=tenant,
            action=action,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="validate_approved_request")
        return request, grant

    def consume_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        grant = consume_approved_request(
            self.sac_root,
            run_id,
            request_id,
            tenant_id=tenant,
            action=action,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
        assert_tenant_match(tenant, grant.tenant_id, operation="consume_approved_request")
        return grant


class LocalAuditStore:
    """Local filesystem audit hash-chain store."""

    def __init__(self, sac_root: Path) -> None:
        self._chain = EnterpriseAuditChain(project_root_for_sac(sac_root))

    def emit(
        self,
        kind: AuditEventKind,
        *,
        tenant_id: str,
        run_id: str,
        actor_id: str,
        payload: dict[str, str] | None = None,
        status: str = "success",
        message: str | None = None,
    ) -> AuditEvent:
        return self._chain.emit(
            kind,
            tenant_id=validate_tenant_id(tenant_id),
            run_id=run_id,
            actor_id=actor_id,
            payload=payload,
            status=status,
            message=message,
        )

    def verify_integrity(self) -> tuple[bool, str]:
        return self._chain.verify_integrity()

    def list_events(self, *, tenant_id: str, run_id: str | None = None) -> list[AuditEvent]:
        return filter_audit_events_by_tenant(
            self._chain.iter_events(),
            validate_tenant_id(tenant_id),
            run_id=run_id,
        )

    def tamper_first_event_for_test(self) -> None:
        if not self._chain.log_file.is_file():
            raise RuntimeError("no audit events to tamper")
        lines = self._chain.log_file.read_text(encoding="utf-8").splitlines()
        payload = json.loads(lines[0])
        payload["message"] = "tampered"
        lines[0] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._chain.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


class LocalEvidenceStore:
    """Local filesystem evidence bundle store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def export_run_evidence(self, *, tenant_id: str, run_id: str) -> Path:
        from safecode.enterprise.evidence.export import export_run_evidence

        return export_run_evidence(
            self.sac_root,
            run_id,
            tenant_id=validate_tenant_id(tenant_id),
        )


class LocalEvalResultStore:
    """Local filesystem evaluation result store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def write_results(
        self, *, tenant_id: str, run_id: str, results: list[EvaluationResult]
    ) -> Path:
        validate_tenant_id(tenant_id)
        from safecode.enterprise.eval.runner import write_results as persist_eval_results

        return persist_eval_results(results, self.sac_root, run_id)

    def read_results(self, *, tenant_id: str, run_id: str) -> list[EvaluationResult]:
        validate_tenant_id(tenant_id)
        path = self.sac_root / "enterprise" / "eval" / "results" / run_id / "results.json"
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [EvaluationResult.model_validate(item) for item in payload]


class LocalTraceStore:
    """Local filesystem trace and timeline store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def emit_event(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_type: TraceEventType | str,
        node_id: str,
        seq: int,
        payload: dict[str, object] | None = None,
        actor_id: str | None = None,
        policy_snapshot_id: str | None = None,
        cost: NodeCost | None = None,
        duration_ms: int | None = None,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> TraceEvent | None:
        emitter = TraceEmitter(self.sac_root, run_id)
        return emitter.emit(
            event_type,
            node_id=node_id,
            seq=seq,
            tenant_id=validate_tenant_id(tenant_id),
            payload=payload,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            cost=cost,
            duration_ms=duration_ms,
            event_id=event_id,
            timestamp=timestamp,
        )

    def list_events(self, *, tenant_id: str, run_id: str) -> list[TraceEvent]:
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for item in TraceEmitter(self.sac_root, run_id).iter_events()
            if item.tenant_id == tenant
        ]

    def write_timeline(self, *, tenant_id: str, run_id: str) -> Path:
        validate_tenant_id(tenant_id)
        return write_timeline(self.sac_root, run_id)


@dataclass(frozen=True)
class LocalBackend:
    """Aggregate local filesystem persistence surface for Enterprise workflows."""

    sac_root: Path

    @property
    def runs(self) -> LocalRunStore:
        return LocalRunStore(self.sac_root)

    @property
    def approvals(self) -> LocalApprovalStore:
        return LocalApprovalStore(self.sac_root)

    @property
    def audit(self) -> LocalAuditStore:
        return LocalAuditStore(self.sac_root)

    @property
    def evidence(self) -> LocalEvidenceStore:
        return LocalEvidenceStore(self.sac_root)

    @property
    def eval_results(self) -> LocalEvalResultStore:
        return LocalEvalResultStore(self.sac_root)

    @property
    def trace(self) -> LocalTraceStore:
        return LocalTraceStore(self.sac_root)

    @property
    def commands(self) -> LocalCommandQueue:
        from safecode.enterprise.worker.queue import LocalCommandQueue

        return LocalCommandQueue(self.sac_root)

    @property
    def leases(self) -> LocalRunLeaseStore:
        from safecode.enterprise.worker.lease import LocalRunLeaseStore

        return LocalRunLeaseStore(self.sac_root)

    @property
    def webhooks(self) -> LocalWebhookEventStore:
        return LocalWebhookEventStore(self.sac_root)

    def probe(self) -> bool:
        """Return whether the local backend storage is usable."""
        try:
            target = self.sac_root / "enterprise"
            target.mkdir(parents=True, exist_ok=True)
            probe_file = target / ".probe"
            probe_file.write_text("ok", encoding="utf-8")
            return probe_file.is_file()
        except OSError:
            return False
