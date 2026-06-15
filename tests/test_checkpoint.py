"""Tests for checkpoint and rollback behavior."""

import hashlib
from pathlib import Path

import pytest

from safecode.checkpoint.manager import CheckpointIntegrityError, CheckpointManager
from safecode.patch.models import PatchBlock, PatchProposal


def make_proposal() -> PatchProposal:
    return PatchProposal(
        id="patch_checkpoint",
        task="checkpoint test",
        blocks=[
            PatchBlock(
                operation="update",
                file_path=Path("README.md"),
                search="before",
                replace="after",
            )
        ],
        created_at="2026-05-21T12:30:00Z",
        model="mock",
    )


def test_create_checkpoint_backs_up_existing_file(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("before\n", encoding="utf-8")

    metadata = CheckpointManager(tmp_path).create(make_proposal())

    checkpoint_dir = tmp_path / ".sac" / "checkpoints" / metadata.checkpoint_id
    assert (checkpoint_dir / "metadata.json").exists()
    assert (checkpoint_dir / "files" / "README.md").read_text(encoding="utf-8") == "before\n"

    operation = metadata.file_operations[0]
    assert operation.path == "README.md"
    assert operation.operation == "update"
    assert operation.existed_before is True
    assert operation.backup_path == "files/README.md"


def test_rollback_last_restores_existing_file(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("before\n", encoding="utf-8")
    manager = CheckpointManager(tmp_path)
    metadata = manager.create(make_proposal())

    readme.write_text("after\n", encoding="utf-8")
    restored = manager.rollback_last()

    assert restored.checkpoint_id == metadata.checkpoint_id
    assert readme.read_text(encoding="utf-8") == "before\n"


# ---------------------------------------------------------------------------
# B13 fix: checkpoint integrity (sha256 verification)
# ---------------------------------------------------------------------------

def test_create_stores_sha256_in_file_operation(tmp_path) -> None:
    """B13: create() stores sha256 of each backed-up file."""
    readme = tmp_path / "README.md"
    readme.write_text("before\n", encoding="utf-8")

    metadata = CheckpointManager(tmp_path).create(make_proposal())

    operation = metadata.file_operations[0]
    assert operation.backup_sha256 is not None
    expected = hashlib.sha256(b"before\n").hexdigest()
    assert operation.backup_sha256 == expected


def test_restore_passes_when_sha256_matches(tmp_path) -> None:
    """B13: restore succeeds when backup sha256 matches stored value."""
    readme = tmp_path / "README.md"
    readme.write_text("before\n", encoding="utf-8")
    manager = CheckpointManager(tmp_path)
    manager.create(make_proposal())
    readme.write_text("after\n", encoding="utf-8")

    # Must not raise.
    manager.rollback_last()
    assert readme.read_text(encoding="utf-8") == "before\n"


def test_restore_raises_integrity_error_on_corrupt_backup(tmp_path) -> None:
    """B13: restore raises CheckpointIntegrityError when backup is corrupted."""
    readme = tmp_path / "README.md"
    readme.write_text("before\n", encoding="utf-8")
    manager = CheckpointManager(tmp_path)
    metadata = manager.create(make_proposal())

    # Corrupt the backup file after creating the checkpoint.
    checkpoint_dir = tmp_path / ".sac" / "checkpoints" / metadata.checkpoint_id
    backup_file = checkpoint_dir / "files" / "README.md"
    backup_file.write_text("CORRUPTED\n", encoding="utf-8")

    readme.write_text("after\n", encoding="utf-8")
    with pytest.raises(CheckpointIntegrityError) as exc_info:
        manager.rollback_last()

    assert "README.md" in str(exc_info.value)
    assert metadata.checkpoint_id in str(exc_info.value)
    # Verify target was NOT touched (abort before restore).
    assert readme.read_text(encoding="utf-8") == "after\n"


def test_restore_skips_sha256_check_for_old_checkpoint(tmp_path) -> None:
    """B13: old checkpoints without backup_sha256 are still restorable (backward compat)."""
    readme = tmp_path / "README.md"
    readme.write_text("before\n", encoding="utf-8")
    manager = CheckpointManager(tmp_path)
    metadata = manager.create(make_proposal())

    # Simulate an old checkpoint: patch the operation to remove sha256.
    import json
    checkpoint_dir = tmp_path / ".sac" / "checkpoints" / metadata.checkpoint_id
    meta_path = checkpoint_dir / "metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    for op in data["file_operations"]:
        op.pop("backup_sha256", None)
        op["backup_sha256"] = None
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    readme.write_text("after\n", encoding="utf-8")
    # Must not raise — skip verification for sha256=None.
    manager.rollback_last()
    assert readme.read_text(encoding="utf-8") == "before\n"


def test_checkpoint_integrity_error_attributes(tmp_path) -> None:
    """CheckpointIntegrityError exposes path, checkpoint_id, expected, actual."""
    exc = CheckpointIntegrityError("foo.py", "chkpt-1", "abc123", "def456")
    assert exc.path == "foo.py"
    assert exc.checkpoint_id == "chkpt-1"
    assert exc.expected == "abc123"
    assert exc.actual == "def456"
    assert "foo.py" in str(exc)
