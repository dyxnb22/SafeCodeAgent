"""Governed long-term memory fact store (v2.4.6)."""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.approvals.store import Action, consume_approved_request, load_request
from safecode.enterprise.memory.models import MemoryFact, MemoryFactStatus
from safecode.enterprise.tenancy import validate_tenant_id
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.workflow.exceptions import WorkflowError


class MemoryGovernanceError(Exception):
    """Memory governance error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def memory_admission_target(
    *,
    content: str,
    provenance: str,
    expires_at: str,
    permission_scope: list[str] | None = None,
) -> dict[str, str]:
    redacted = redact_secrets(content.strip())
    scope = sorted(set(permission_scope or ["org", "appsec"]))
    target = {
        "content_sha256": hashlib.sha256(redacted.encode("utf-8")).hexdigest(),
        "provenance_sha256": hashlib.sha256(provenance.strip().encode("utf-8")).hexdigest(),
        "expires_at": expires_at,
        "permission_scope": json.dumps(scope, separators=(",", ":")),
    }
    return dict(sorted(target.items()))


def memory_facts_dir(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "memory_facts"


def _tenant_file(sac_root: Path, tenant_id: str) -> Path:
    tenant = validate_tenant_id(tenant_id)
    root = memory_facts_dir(sac_root).resolve()
    path = (root / f"{tenant}.json").resolve()
    if path.parent != root:
        raise MemoryGovernanceError("tenant memory path escapes memory root")
    return path


class MemoryFactStore:
    """Local file-backed store for governed memory facts."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def _load(self, tenant_id: str) -> dict[str, MemoryFact]:
        path = _tenant_file(self.sac_root, tenant_id)
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise MemoryGovernanceError("memory facts file is corrupted")
        facts: dict[str, MemoryFact] = {}
        for item in payload:
            fact = MemoryFact.model_validate(item)
            facts[fact.fact_id] = fact
        return facts

    def _save(self, tenant_id: str, facts: dict[str, MemoryFact]) -> None:
        path = _tenant_file(self.sac_root, tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = [facts[key].model_dump(mode="json") for key in sorted(facts)]
        path.write_text(json.dumps(ordered, indent=2), encoding="utf-8")

    def _audit(
        self,
        *,
        kind: AuditEventKind,
        tenant_id: str,
        fact_id: str,
        actor_id: str,
        payload: dict[str, str],
    ) -> None:
        audit = EnterpriseAuditChain(project_root_for_sac(self.sac_root))
        audit.emit(
            kind,
            run_id=f"memory-{fact_id}",
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload={"fact_id": fact_id, **payload},
        )

    def admit(
        self,
        *,
        tenant_id: str,
        content: str,
        provenance: str,
        actor_id: str,
        run_id: str,
        request_id: str,
        policy_snapshot_id: str,
        expires_at: str,
        permission_scope: list[str] | None = None,
        fact_id: str | None = None,
    ) -> MemoryFact:
        tenant = validate_tenant_id(tenant_id)
        redacted = redact_secrets(content.strip())
        if not redacted:
            raise MemoryGovernanceError("memory fact content must not be empty")
        if not provenance.strip():
            raise MemoryGovernanceError("provenance is required")
        try:
            _parse_ts(expires_at)
        except (TypeError, ValueError) as exc:
            raise MemoryGovernanceError("expires_at must be an ISO-8601 timestamp") from exc
        scope = sorted(set(permission_scope or ["org", "appsec"]))
        fid = fact_id or f"fact-{uuid.uuid4().hex[:12]}"
        facts = self._load(tenant)
        if fid in facts:
            raise MemoryGovernanceError(f"memory fact already exists: {fid}")
        target = memory_admission_target(
            content=redacted,
            provenance=provenance,
            expires_at=expires_at,
            permission_scope=scope,
        )
        try:
            grant = consume_approved_request(
                self.sac_root,
                run_id,
                request_id,
                tenant_id=tenant,
                action=Action.memory_fact_inject,
                policy_snapshot_id=policy_snapshot_id,
                target=target,
            )
            approval = load_request(self.sac_root, run_id, request_id)
        except (PermissionError, WorkflowError) as exc:
            raise MemoryGovernanceError(f"memory admission grant denied: {exc}") from exc
        if not approval.decision_actor:
            raise MemoryGovernanceError("approved memory request has no human approver")
        now = _utc_now()
        fact = MemoryFact(
            tenant_id=tenant,
            fact_id=fid,
            content=redacted,
            provenance=provenance.strip(),
            approver=approval.decision_actor,
            approval_request_id=request_id,
            approval_grant_id=grant.grant_id,
            policy_snapshot_id=policy_snapshot_id,
            admitted_at=now,
            expires_at=expires_at,
            status="active",
            permission_scope=scope,
        )
        facts[fid] = fact
        self._save(tenant, facts)
        self._audit(
            kind=AuditEventKind.tool_call_executed,
            tenant_id=tenant,
            fact_id=fid,
            actor_id=actor_id,
            payload={"operation": "memory_fact_admitted", "provenance": fact.provenance, "approver": fact.approver},
        )
        return fact

    def revoke(self, *, tenant_id: str, fact_id: str, actor_id: str, reason: str = "") -> MemoryFact:
        facts = self._load(tenant_id)
        fact = facts.get(fact_id)
        if fact is None:
            raise MemoryGovernanceError(f"memory fact not found: {fact_id}")
        if fact.status == "revoked":
            return fact
        updated = fact.model_copy(update={"status": "revoked", "revoked_at": _utc_now()})
        facts[fact_id] = updated
        self._save(tenant_id, facts)
        self._audit(
            kind=AuditEventKind.tool_call_blocked,
            tenant_id=tenant_id,
            fact_id=fact_id,
            actor_id=actor_id,
            payload={"operation": "memory_fact_revoked", "reason": reason[:256]},
        )
        return updated

    def expire_due(self, *, tenant_id: str, actor_id: str, now: str | None = None) -> list[MemoryFact]:
        current = _parse_ts(now or _utc_now())
        facts = self._load(tenant_id)
        expired: list[MemoryFact] = []
        for fact_id, fact in facts.items():
            if fact.status != "active" or not fact.expires_at:
                continue
            if _parse_ts(fact.expires_at) <= current:
                updated = fact.model_copy(update={"status": "expired"})
                facts[fact_id] = updated
                expired.append(updated)
                self._audit(
                    kind=AuditEventKind.tool_call_blocked,
                    tenant_id=tenant_id,
                    fact_id=fact_id,
                    actor_id=actor_id,
                    payload={"operation": "memory_fact_expired"},
                )
        if expired:
            self._save(tenant_id, facts)
        return expired

    def get(self, *, tenant_id: str, fact_id: str) -> MemoryFact | None:
        return self._load(tenant_id).get(fact_id)

    def list_active(
        self,
        tenant_id: str,
        *,
        actor_scope: set[str] | None = None,
    ) -> list[MemoryFact]:
        self.expire_due(tenant_id=tenant_id, actor_id="system:memory")
        facts = [fact for fact in self._load(tenant_id).values() if fact.status == "active"]
        if actor_scope is not None:
            facts = [fact for fact in facts if set(fact.permission_scope).issubset(actor_scope)]
        return facts

    def list_all(self, tenant_id: str) -> list[MemoryFact]:
        return list(self._load(tenant_id).values())
