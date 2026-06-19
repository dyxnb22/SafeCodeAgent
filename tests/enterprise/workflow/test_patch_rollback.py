"""Patch checkpoint and rollback tests."""

from pathlib import Path

from safecode.enterprise.workflow.remediation_patch import (
    apply_with_checkpoint,
    file_sha256,
    rollback_last,
)
from safecode.patch.models import PatchBlock, PatchProposal


def test_rollback_restores_file_hash(tmp_path: Path):
    target = tmp_path / "app.py"
    original = 'query = f"SELECT * FROM users WHERE id={user_id}"\n'
    target.write_text(original, encoding="utf-8")
    before = file_sha256(target)
    proposal = PatchProposal(
        id="patch-rollback-test",
        task="test rollback",
        blocks=[
            PatchBlock(
                operation="update",
                file_path=Path("app.py"),
                search=original.strip(),
                replace='query = "SELECT * FROM users WHERE id=?"',
            )
        ],
        created_at="2026-06-19T00:00:00+00:00",
        model="mock",
    )
    apply_with_checkpoint(tmp_path, proposal)
    assert file_sha256(target) != before
    rollback_last(tmp_path)
    assert file_sha256(target) == before
