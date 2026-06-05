"""Tests for v4.18.0 per-patch undo and checkpoint granularity."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.checkpoint.manager import CheckpointManager
from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.patch.models import PatchBlock, PatchProposal


def _make_proposal(tmp_path: Path, filename: str = "test.txt") -> PatchProposal:
    """Create a PatchProposal and a real file for checkpoint testing."""
    file_path = tmp_path / filename
    file_path.write_text("original content")
    return PatchProposal(
        id="patch_test1",
        task="test task",
        model="mock",
        blocks=[PatchBlock(
            operation="update",
            file_path=file_path.relative_to(tmp_path),
            search="original content",
            replace="updated content",
        )],
        created_at="2026-01-01T00:00:00",
    )


def test_checkpoint_manager_list_empty(tmp_path: Path):
    """list_checkpoints returns empty list when no checkpoints exist."""
    mgr = CheckpointManager(tmp_path)
    result = mgr.list_checkpoints()
    assert result == []


def test_checkpoint_manager_create_and_list(tmp_path: Path):
    """checkpoints can be created and listed."""
    proposal = _make_proposal(tmp_path)
    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)
    assert metadata.checkpoint_id
    assert metadata.patch_id == "patch_test1"

    checkpoints = mgr.list_checkpoints()
    assert len(checkpoints) == 1
    assert checkpoints[0].checkpoint_id == metadata.checkpoint_id


def test_checkpoint_manager_rollback_by_id(tmp_path: Path):
    """Can rollback a specific checkpoint by ID."""
    proposal = _make_proposal(tmp_path)
    file_path = tmp_path / "test.txt"
    original = file_path.read_text()

    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)

    # Modify the file
    file_path.write_text("modified content")

    # Rollback by checkpoint ID
    result = mgr.rollback_by_checkpoint_id(metadata.checkpoint_id)
    assert result.checkpoint_id == metadata.checkpoint_id
    assert file_path.read_text() == original


def test_checkpoint_manager_rollback_by_id_not_found(tmp_path: Path):
    """Rollback by unknown checkpoint ID raises FileNotFoundError."""
    mgr = CheckpointManager(tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.rollback_by_checkpoint_id("nonexistent")


def test_checkpoint_rollback_last_still_works(tmp_path: Path):
    """rollback_last still works after per-patch changes."""
    proposal = _make_proposal(tmp_path)
    file_path = tmp_path / "test.txt"
    original = file_path.read_text()

    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)
    file_path.write_text("modified content")

    result = mgr.rollback_last()
    assert result.checkpoint_id == metadata.checkpoint_id
    assert file_path.read_text() == original


def test_orchestrator_list_checkpoints(tmp_path: Path):
    """AgentOrchestrator.list_checkpoints delegates to CheckpointManager."""
    from safecode.agent.orchestrator import AgentOrchestrator
    proposal = _make_proposal(tmp_path)
    mgr = CheckpointManager(tmp_path)
    mgr.create(proposal)

    orch = AgentOrchestrator(tmp_path)
    result = orch.list_checkpoints()
    assert len(result) == 1


def test_orchestrator_rollback_checkpoint(tmp_path: Path):
    """AgentOrchestrator.rollback_checkpoint restores a specific checkpoint."""
    from safecode.agent.orchestrator import AgentOrchestrator
    proposal = _make_proposal(tmp_path)
    file_path = tmp_path / "test.txt"
    original = file_path.read_text()

    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)
    file_path.write_text("modified content")

    orch = AgentOrchestrator(tmp_path)
    result = orch.rollback_checkpoint(metadata.checkpoint_id)
    assert result.checkpoint.checkpoint_id == metadata.checkpoint_id
    assert file_path.read_text() == original
