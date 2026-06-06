"""Tests for v4.18.0 per-patch undo and checkpoint granularity.

Includes v4.18.2 safety regression fix tests: verifying that --checkpoint
is gated identically to --last (ToolCallGate, committed-checkpoint refusal,
task sidecar wiring).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.checkpoint.manager import CheckpointManager
from safecode.checkpoint.models import CheckpointFileOperation, CheckpointMetadata
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.tools.gate import GateResult

runner = CliRunner()


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


# ---------------------------------------------------------------------------
# v4.18.2 safety regression fix: --checkpoint must be gated identically to
# --last (ToolCallGate + committed-checkpoint guard + task sidecar wiring).
# ---------------------------------------------------------------------------

def _make_cli_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with a .sac/config.toml."""
    (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".sac" / "config.toml").write_text(
        '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
        'base_url = "http://localhost:8080/v1"\n'
        "[sandbox]\nnetwork_enabled = false\n",
        encoding="utf-8",
    )
    return tmp_path


def test_rollback_checkpoint_blocked_by_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--checkpoint path refuses when ToolCallGate denies the operation."""
    from safecode.cli import app

    monkeypatch.chdir(_make_cli_project(tmp_path))

    proposal = _make_proposal(tmp_path)
    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)

    denied = GateResult(allowed=False, reason="gate blocked in test")
    with patch("safecode.cli_core.ToolCallGate") as mock_gate_cls:
        mock_gate_cls.return_value.check_intent.return_value = denied
        result = runner.invoke(app, ["rollback", "--checkpoint", metadata.checkpoint_id])

    assert result.exit_code == 1
    assert "Blocked by tool gate" in result.output


def test_rollback_checkpoint_refused_when_committed_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--checkpoint refuses when files appear committed and --force-uncommit is absent."""
    from safecode.cli import app

    monkeypatch.chdir(_make_cli_project(tmp_path))

    proposal = _make_proposal(tmp_path)
    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)

    allowed = GateResult(allowed=True, reason="ok")
    with patch("safecode.cli_core.ToolCallGate") as mock_gate_cls, \
         patch("safecode.git.local.is_git_repo", return_value=True), \
         patch("safecode.git.local.worktree_has_changes_for_files", return_value=False), \
         patch("safecode.git.local.commit_contains_files_or_checkpoint", return_value="abc1234"):
        mock_gate_cls.return_value.check_intent.return_value = allowed
        result = runner.invoke(app, ["rollback", "--checkpoint", metadata.checkpoint_id])

    assert result.exit_code == 1
    assert "Rollback refused" in result.output
    assert "committed" in result.output.lower()


def test_rollback_checkpoint_allowed_with_force_uncommit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--checkpoint + --force-uncommit bypasses the committed-checkpoint guard."""
    from safecode.cli import app

    monkeypatch.chdir(_make_cli_project(tmp_path))

    proposal = _make_proposal(tmp_path)
    file_path = tmp_path / "test.txt"
    original = file_path.read_text()
    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)
    file_path.write_text("modified content")

    allowed = GateResult(allowed=True, reason="ok")
    with patch("safecode.cli_core.ToolCallGate") as mock_gate_cls, \
         patch("safecode.git.local.is_git_repo", return_value=True), \
         patch("safecode.git.local.worktree_has_changes_for_files", return_value=False), \
         patch("safecode.git.local.commit_contains_files_or_checkpoint", return_value="abc1234"):
        mock_gate_cls.return_value.check_intent.return_value = allowed
        result = runner.invoke(
            app, ["rollback", "--checkpoint", metadata.checkpoint_id, "--force-uncommit"]
        )

    assert result.exit_code == 0
    assert "Rolled back checkpoint" in result.output
    assert file_path.read_text() == original


def test_rollback_checkpoint_emits_audit_event_with_correct_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--checkpoint path emits a rollback_completed audit event naming the specific checkpoint."""
    from safecode.cli import app
    from safecode.audit.logger import AuditLogger

    monkeypatch.chdir(_make_cli_project(tmp_path))

    proposal = _make_proposal(tmp_path)
    file_path = tmp_path / "test.txt"
    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)
    file_path.write_text("modified content")

    emitted: list = []
    original_write = AuditLogger.write

    def capturing_write(self, event, *, task_id=None):
        emitted.append(event)
        original_write(self, event, task_id=task_id)

    allowed = GateResult(allowed=True, reason="ok")
    with patch("safecode.cli_core.ToolCallGate") as mock_gate_cls, \
         patch.object(AuditLogger, "write", capturing_write):
        mock_gate_cls.return_value.check_intent.return_value = allowed
        result = runner.invoke(app, ["rollback", "--checkpoint", metadata.checkpoint_id])

    assert result.exit_code == 0
    rollback_events = [e for e in emitted if e.type == "rollback_completed"]
    assert rollback_events, "Expected at least one rollback_completed audit event"
    assert rollback_events[0].checkpoint_id == metadata.checkpoint_id


def test_rollback_checkpoint_creates_task_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--checkpoint path calls get_or_create_current_task for sidecar wiring."""
    from safecode.cli import app

    monkeypatch.chdir(_make_cli_project(tmp_path))

    proposal = _make_proposal(tmp_path)
    file_path = tmp_path / "test.txt"
    mgr = CheckpointManager(tmp_path)
    metadata = mgr.create(proposal)
    file_path.write_text("modified content")

    allowed = GateResult(allowed=True, reason="ok")
    with patch("safecode.cli_core.ToolCallGate") as mock_gate_cls, \
         patch("safecode.cli_core.get_or_create_current_task") as mock_task:
        mock_gate_cls.return_value.check_intent.return_value = allowed
        mock_task.return_value = MagicMock(task_id="task-rollback-test")
        result = runner.invoke(app, ["rollback", "--checkpoint", metadata.checkpoint_id])

    assert result.exit_code == 0
    mock_task.assert_called_once_with(tmp_path, "rollback")
