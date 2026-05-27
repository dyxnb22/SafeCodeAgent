"""Tests for checkpoint and rollback behavior."""

from pathlib import Path

from safecode.checkpoint.manager import CheckpointManager
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
