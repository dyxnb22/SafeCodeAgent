"""Checkpoint metadata models.

中文模块说明：内核 checkpoint 元数据模型，记录文件快照与回滚点。
- 架构位置：kernel Checkpoint 平面；Enterprise workflow checkpoint 在此基础上扩展。
- 安全不变量：写工作流必须可回滚或审计补偿；checkpoint 含内容 hash。
- 学习路径：读 ``checkpoint/manager.py`` 与 ``workflow/checkpoint.py``。
"""

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
    session_id: str | None = None  # v5.1.0: agent session that created this checkpoint
