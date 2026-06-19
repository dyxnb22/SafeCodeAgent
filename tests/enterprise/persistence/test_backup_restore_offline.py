"""Backup and restore offline tests (v2.5.4)."""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import pytest

from safecode.audit.models import AuditEvent
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.persistence.local_backend import LocalBackend

_ROOT = Path(__file__).resolve().parents[3]
_BACKUP_SCRIPT = _ROOT / "scripts" / "enterprise-backup.sh"
_RESTORE_SCRIPT = _ROOT / "scripts" / "enterprise-restore.sh"


def _run_script(script: Path, *args: str) -> None:
    subprocess.run(["bash", str(script), *args], check=True, capture_output=True, text=True)


def _verify_hash_chain(log_path: Path) -> None:
    previous_hash: str | None = None
    for line_number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        event = AuditEvent.model_validate_json(line)
        assert event.previous_hash == previous_hash, f"chain break at line {line_number}"
        assert event.event_hash
        previous_hash = event.event_hash


def test_backup_restore_round_trip_preserves_audit_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    anchor_dir = tmp_path / "audit-anchors"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
    sac_root = source / ".sac"
    backend = LocalBackend(sac_root)
    backend.audit.emit(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-backup001",
        actor_id="user:test",
    )
    backend.audit.emit(
        AuditEventKind.workflow_end,
        tenant_id="tenant-a",
        run_id="run-backup001",
        actor_id="user:test",
    )
    ok, message = backend.audit.verify_integrity()
    assert ok, message

    archive = tmp_path / "backup.tar.gz"
    _run_script(_BACKUP_SCRIPT, str(sac_root), str(archive))
    assert archive.is_file()
    with tarfile.open(archive, "r:gz") as handle:
        names = handle.getnames()
    assert any("events.jsonl" in name for name in names)

    restore_parent = tmp_path / "restored"
    _run_script(_RESTORE_SCRIPT, str(archive), str(restore_parent))
    restored_sac = restore_parent / "source" / ".sac"
    assert restored_sac.is_dir()
    original_log = sac_root / "logs" / "events.jsonl"
    restored_log = restored_sac / "logs" / "events.jsonl"
    assert restored_log.is_file()
    assert original_log.read_text(encoding="utf-8") == restored_log.read_text(encoding="utf-8")
    _verify_hash_chain(restored_log)
    restored = LocalBackend(restored_sac)
    events = restored.audit.list_events(tenant_id="tenant-a", run_id="run-backup001")
    assert len(events) == 2
