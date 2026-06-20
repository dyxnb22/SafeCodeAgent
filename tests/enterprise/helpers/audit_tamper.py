"""Test-only helpers for corrupting audit chains in integrity tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.trace.session import project_root_for_sac


def tamper_first_local_audit_chain(sac_root: Path) -> None:
    """Corrupt the first event in a local enterprise audit hash chain."""
    chain = EnterpriseAuditChain(project_root_for_sac(sac_root))
    if not chain.log_file.is_file():
        raise RuntimeError("no audit events to tamper")
    lines = chain.log_file.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["message"] = "tampered"
    lines[0] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    chain.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tamper_first_postgres_audit(backend: object) -> None:
    """Corrupt the first persisted audit event in a Postgres backend."""
    uow = getattr(backend, "_uow", None)
    if uow is None:
        raise RuntimeError("backend does not expose postgres unit of work")
    with uow.connection() as conn:
        row = conn.execute(
            "SELECT id, event FROM enterprise.audit_events ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("no audit events to tamper")
        event_id, payload = row
        event = dict(payload)
        event["message"] = "tampered"
        conn.execute(
            "UPDATE enterprise.audit_events SET event = %s::jsonb WHERE id = %s",
            (json.dumps(event, ensure_ascii=False, sort_keys=True), event_id),
        )
        conn.commit()


def tamper_backend_first_audit_event(backend: object) -> None:
    """Route tampering to the appropriate test helper for a backend implementation."""
    if hasattr(backend, "_uow"):
        tamper_first_postgres_audit(backend)
        return
    sac_root = getattr(backend, "sac_root", None)
    if sac_root is None:
        raise RuntimeError("backend does not expose sac_root for audit tampering")
    tamper_first_local_audit_chain(Path(sac_root))
