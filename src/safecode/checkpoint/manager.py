"""Create checkpoints and restore them during rollback.

中文模块说明：检查点创建与回滚。
- 在 patch 应用前备份受影响文件，元数据记录 sha256；回滚前校验备份完整性（B13）。
- 经 FilesystemBoundary 校验路径，防止越界写入或恢复。
"""

import hashlib
import json
import shutil
from pathlib import Path

from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.patch.models import PatchProposal
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.utils.time import utc_now_iso


class CheckpointIntegrityError(RuntimeError):
    """Raised when a backup file's sha256 does not match the stored value (B13 fix).

    Prevents silent restoration of corrupt or tampered checkpoint backups.
    The checkpoint_id and path are recorded; never attempt a restore of an
    integrity-failing backup — investigate and delete the checkpoint if corrupt.

    备份 sha256 与元数据不一致时抛出；禁止继续恢复，须调查或删除损坏的检查点。
    """

    def __init__(self, path: str, checkpoint_id: str, expected: str, actual: str) -> None:
        self.path = path
        self.checkpoint_id = checkpoint_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Checkpoint integrity failure: backup sha256 mismatch for {path!r} "
            f"in checkpoint {checkpoint_id!r}. "
            f"Expected {expected[:16]}... got {actual[:16]}.... "
            "Do not restore this checkpoint — delete it and re-apply the patch."
        )


def _sha256_of_file(path: Path) -> str:
    """Return lowercase hex sha256 of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class CheckpointManager:
    """Manage .sac/checkpoints.

    管理 ``.sac/checkpoints`` 目录下的备份与元数据；所有目标路径经 FilesystemBoundary 校验。
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.checkpoints_dir = self.project_root / ".sac" / "checkpoints"
        self.filesystem = FilesystemBoundary(self.project_root)

    def create(self, proposal: PatchProposal) -> CheckpointMetadata:
        """Create a checkpoint before applying a patch.

        在应用 patch 前为每个受影响文件创建备份并记录 backup_sha256。
        """
        checkpoint_id = f"{utc_now_iso().replace(':', '-')}_{proposal.id}"
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        files_dir = checkpoint_dir / "files"
        file_operations: list[CheckpointFileOperation] = []

        for block in proposal.blocks:
            target_path = self.filesystem.validate(self.project_root / block.file_path)
            backup_path: str | None = None
            existed_before = target_path.exists()

            backup_sha256: str | None = None
            if existed_before:
                relative_backup = Path("files") / block.file_path
                backup_file = checkpoint_dir / relative_backup
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, backup_file)
                # B13 fix: record sha256 so restore can verify backup integrity.
                backup_sha256 = _sha256_of_file(backup_file)
                backup_path = relative_backup.as_posix()
            else:
                files_dir.mkdir(parents=True, exist_ok=True)

            file_operations.append(
                CheckpointFileOperation(
                    path=block.file_path.as_posix(),
                    operation=block.operation,
                    existed_before=existed_before,
                    backup_path=backup_path,
                    backup_sha256=backup_sha256,
                )
            )

        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            task=proposal.task,
            patch_id=proposal.id,
            created_at=utc_now_iso(),
            file_operations=file_operations,
        )
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / "metadata.json").write_text(
            json.dumps(metadata.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata

    def rollback_last(self) -> CheckpointMetadata:
        """Restore the latest checkpoint."""
        metadata = self._load_latest_metadata()
        self._restore_checkpoint(metadata)
        return metadata

    def rollback_by_checkpoint_id(self, checkpoint_id: str) -> CheckpointMetadata:
        """Restore a specific checkpoint by its ID."""
        metadata = self._load_metadata(checkpoint_id)
        self._restore_checkpoint(metadata)
        return metadata

    def list_checkpoints(self) -> list[CheckpointMetadata]:
        """List all available checkpoints, newest first."""
        if not self.checkpoints_dir.exists():
            return []
        dirs = sorted(
            (p for p in self.checkpoints_dir.iterdir() if p.is_dir()),
            reverse=True,
        )
        result: list[CheckpointMetadata] = []
        for d in dirs:
            metadata_path = d / "metadata.json"
            if metadata_path.exists():
                try:
                    data = json.loads(metadata_path.read_text(encoding="utf-8"))
                    result.append(CheckpointMetadata(**data))
                except Exception:
                    # 损坏的 metadata.json 被静默跳过，调用方可能误以为检查点不存在。
                    pass
        return result

    def _restore_checkpoint(self, metadata: CheckpointMetadata) -> None:
        """Restore files from a checkpoint.

        B13 fix: verifies sha256 of each backup file before copying. If the
        stored sha256 doesn't match the actual backup, raises
        CheckpointIntegrityError and aborts the restore without touching any
        target files.

        先对所有备份做完整性预检，再修改目标文件；任一备份失败则整次回滚中止。
        无 backup_sha256 的旧检查点跳过校验（向后兼容），存在被篡改却无法检测的风险。
        """
        checkpoint_dir = self.checkpoints_dir / metadata.checkpoint_id

        # 预检：在触碰任何目标文件之前验证所有备份 sha256。
        for operation in metadata.file_operations:
            if not operation.existed_before or operation.backup_path is None:
                continue
            if operation.backup_sha256 is None:
                # 旧版检查点无 sha256：跳过校验，向后兼容但无法检测备份被篡改。
                continue
            backup_file = checkpoint_dir / operation.backup_path
            if not backup_file.exists():
                raise FileNotFoundError(f"Missing checkpoint backup file: {backup_file}")
            actual = _sha256_of_file(backup_file)
            if actual != operation.backup_sha256:
                raise CheckpointIntegrityError(
                    path=operation.path,
                    checkpoint_id=metadata.checkpoint_id,
                    expected=operation.backup_sha256,
                    actual=actual,
                )

        for operation in metadata.file_operations:
            target_path = self.filesystem.validate(self.project_root / operation.path)
            if operation.existed_before:
                if operation.backup_path is None:
                    raise ValueError(f"Missing backup path for {operation.path}")
                backup_file = checkpoint_dir / operation.backup_path
                if not backup_file.exists():
                    raise FileNotFoundError(f"Missing checkpoint backup file: {backup_file}")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, target_path)
            elif target_path.exists():
                target_path.unlink()

    def _load_latest_metadata(self) -> CheckpointMetadata:
        """Load metadata for the newest checkpoint directory."""
        if not self.checkpoints_dir.exists():
            raise FileNotFoundError("No checkpoints found.")
        checkpoint_dirs = sorted(path for path in self.checkpoints_dir.iterdir() if path.is_dir())
        if not checkpoint_dirs:
            raise FileNotFoundError("No checkpoints found.")
        return self._load_metadata(checkpoint_dirs[-1].name)

    def _load_metadata(self, checkpoint_id: str) -> CheckpointMetadata:
        """Load metadata for a specific checkpoint by ID."""
        metadata_path = self.checkpoints_dir / checkpoint_id / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return CheckpointMetadata(**data)
