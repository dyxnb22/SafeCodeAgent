"""Create checkpoints and restore them during rollback."""

import json
import shutil
from pathlib import Path

from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.patch.models import PatchProposal
from safecode.utils.time import utc_now_iso


class CheckpointManager:
    """Manage .sac/checkpoints."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.checkpoints_dir = self.project_root / ".sac" / "checkpoints"

    def create(self, proposal: PatchProposal) -> CheckpointMetadata:
        """Create a checkpoint before applying a patch."""
        checkpoint_id = f"{utc_now_iso().replace(':', '-')}_{proposal.id}"
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        files_dir = checkpoint_dir / "files"
        file_operations: list[CheckpointFileOperation] = []

        for block in proposal.blocks:
            target_path = (self.project_root / block.file_path).resolve()
            backup_path: str | None = None
            existed_before = target_path.exists()

            if existed_before:
                relative_backup = Path("files") / block.file_path
                backup_file = checkpoint_dir / relative_backup
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, backup_file)
                backup_path = relative_backup.as_posix()
            else:
                files_dir.mkdir(parents=True, exist_ok=True)

            file_operations.append(
                CheckpointFileOperation(
                    path=block.file_path.as_posix(),
                    operation=block.operation,
                    existed_before=existed_before,
                    backup_path=backup_path,
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
        checkpoint_dir = self.checkpoints_dir / metadata.checkpoint_id

        for operation in metadata.file_operations:
            target_path = (self.project_root / operation.path).resolve()
            try:
                target_path.relative_to(self.project_root)
            except ValueError as exc:
                raise ValueError(f"Checkpoint path escapes project root: {operation.path}") from exc

            if operation.existed_before:
                if operation.backup_path is None:
                    raise ValueError(f"Missing backup path for {operation.path}")
                backup_file = checkpoint_dir / operation.backup_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, target_path)
            elif target_path.exists():
                target_path.unlink()

        return metadata

    def _load_latest_metadata(self) -> CheckpointMetadata:
        """Load metadata for the newest checkpoint directory."""
        if not self.checkpoints_dir.exists():
            raise FileNotFoundError("No checkpoints found.")

        checkpoint_dirs = sorted(path for path in self.checkpoints_dir.iterdir() if path.is_dir())
        if not checkpoint_dirs:
            raise FileNotFoundError("No checkpoints found.")

        metadata_path = checkpoint_dirs[-1] / "metadata.json"
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return CheckpointMetadata(**data)
