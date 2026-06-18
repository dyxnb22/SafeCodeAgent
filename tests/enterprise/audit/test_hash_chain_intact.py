"""Enterprise audit hash-chain integration tests."""

import json
from pathlib import Path

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind


def test_hash_chain_intact_after_emits(tmp_path: Path):
    audit = EnterpriseAuditChain(tmp_path)
    audit.emit(AuditEventKind.workflow_start, run_id="run-audit01", actor_id="user:test")
    audit.emit(AuditEventKind.approval_requested, run_id="run-audit01", actor_id="user:test")
    ok, message = audit.verify_integrity()
    assert ok, message


def test_tampering_breaks_chain(tmp_path: Path):
    audit = EnterpriseAuditChain(tmp_path)
    audit.emit(AuditEventKind.workflow_start, run_id="run-audit02", actor_id="user:test")
    audit.emit(AuditEventKind.workflow_end, run_id="run-audit02", actor_id="user:test")
    lines = audit.log_file.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["message"] = "tampered"
    lines[0] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    audit.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, message = audit.verify_integrity()
    assert not ok
    assert "mismatch" in message.lower() or "break" in message.lower()
