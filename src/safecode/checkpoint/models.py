"""Checkpoint metadata models."""

from pydantic import BaseModel


class CheckpointFileOperation(BaseModel):
    """How one file should be restored during rollback."""

    path: str
    operation: str
    existed_before: bool
    backup_path: str | None = None
    backup_sha256: str | None = None  # B13: sha256 of the backup file; None on old checkpoints


class CheckpointMetadata(BaseModel):
    """Metadata stored beside checkpoint file backups."""

    checkpoint_id: str
    task: str
    patch_id: str
    created_at: str
    file_operations: list[CheckpointFileOperation]
