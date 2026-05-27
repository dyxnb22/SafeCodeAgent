"""Coordinate context collection, LLM responses, patch handling, and audit logs."""

import json
from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.checkpoint.manager import CheckpointManager
from safecode.checkpoint.models import CheckpointMetadata
from safecode.context.collector import ContextCollector
from safecode.llm.mock import MockLLMClient
from safecode.patch.applier import PatchApplier
from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchProposal
from safecode.patch.parser import PatchParser
from safecode.patch.validator import PatchValidator
from safecode.utils.time import utc_now_iso


@dataclass
class EditResult:
    """Result returned by sac edit before any file is modified."""

    proposal: PatchProposal
    diff_text: str
    pending_patch_path: Path


@dataclass
class ApplyPreview:
    """Validated pending patch preview before user approval."""

    proposal: PatchProposal
    diff_text: str
    pending_patch_path: Path


@dataclass
class ApplyResult:
    """Result after a pending patch has been applied."""

    proposal: PatchProposal
    checkpoint: CheckpointMetadata
    files: list[str]


@dataclass
class RollbackResult:
    """Result after restoring the latest checkpoint."""

    checkpoint: CheckpointMetadata
    files: list[str]


class AgentOrchestrator:
    """High-level workflow entrypoint for v0.1 commands."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.context_collector = ContextCollector(project_root)
        self.llm_client = MockLLMClient()
        self.audit_logger = AuditLogger(project_root)

    def ask(self, question: str) -> str:
        """Return a read-only answer about the current project."""
        context = self.context_collector.collect()
        answer = self.llm_client.ask(question, context)
        self.audit_logger.write(
            AuditEvent(
                type="ask_completed",
                timestamp=utc_now_iso(),
                message=question,
            )
        )
        return answer.content

    def edit(self, task: str) -> EditResult:
        """Generate and store a pending patch proposal."""
        context = self.context_collector.collect()
        patch_response = self.llm_client.propose_patch(task, context)
        proposal = PatchParser().parse(patch_response.patch_text, task=task)

        PatchValidator(self.project_root).validate(proposal)
        diff_text = build_unified_diff(self.project_root, proposal)
        pending_patch_path = self._save_pending_patch(proposal)

        self.audit_logger.write(
            AuditEvent(
                type="patch_proposed",
                timestamp=utc_now_iso(),
                patch_id=proposal.id,
                files=[block.file_path.as_posix() for block in proposal.blocks],
                message=task,
            )
        )
        return EditResult(
            proposal=proposal,
            diff_text=diff_text,
            pending_patch_path=pending_patch_path,
        )

    def preview_apply(self) -> ApplyPreview:
        """Load, validate, and diff the pending patch without writing files."""
        pending_patch_path = self._pending_patch_path()
        proposal = self._load_pending_patch(pending_patch_path)

        PatchValidator(self.project_root).validate(proposal)
        diff_text = build_unified_diff(self.project_root, proposal)
        return ApplyPreview(
            proposal=proposal,
            diff_text=diff_text,
            pending_patch_path=pending_patch_path,
        )

    def apply(self, proposal: PatchProposal) -> ApplyResult:
        """Checkpoint and apply a previously previewed pending patch."""
        PatchValidator(self.project_root).validate(proposal)
        checkpoint = CheckpointManager(self.project_root).create(proposal)
        PatchApplier(self.project_root).apply(proposal)
        self._pending_patch_path().unlink(missing_ok=True)

        files = [block.file_path.as_posix() for block in proposal.blocks]
        self.audit_logger.write(
            AuditEvent(
                type="checkpoint_created",
                timestamp=utc_now_iso(),
                patch_id=proposal.id,
                checkpoint_id=checkpoint.checkpoint_id,
                files=files,
                message=proposal.task,
            )
        )
        self.audit_logger.write(
            AuditEvent(
                type="patch_applied",
                timestamp=utc_now_iso(),
                patch_id=proposal.id,
                checkpoint_id=checkpoint.checkpoint_id,
                files=files,
                message=proposal.task,
            )
        )
        return ApplyResult(proposal=proposal, checkpoint=checkpoint, files=files)

    def rollback_last(self) -> RollbackResult:
        """Restore the latest checkpoint and audit the rollback."""
        checkpoint = CheckpointManager(self.project_root).rollback_last()
        files = [operation.path for operation in checkpoint.file_operations]
        self.audit_logger.write(
            AuditEvent(
                type="rollback_completed",
                timestamp=utc_now_iso(),
                patch_id=checkpoint.patch_id,
                checkpoint_id=checkpoint.checkpoint_id,
                files=files,
                message=checkpoint.task,
            )
        )
        return RollbackResult(checkpoint=checkpoint, files=files)

    def history(self, limit: int = 20) -> list[AuditEvent]:
        """Read recent audit events."""
        return self.audit_logger.read_recent(limit=limit)

    def _save_pending_patch(self, proposal: PatchProposal) -> Path:
        """Save the parsed proposal for a future sac apply command."""
        pending_patch_path = self._pending_patch_path()
        pending_patch_path.parent.mkdir(parents=True, exist_ok=True)
        pending_patch_path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        return pending_patch_path

    def _pending_patch_path(self) -> Path:
        """Return the project pending patch path."""
        return self.project_root / ".sac" / "pending_patch.json"

    def _load_pending_patch(self, pending_patch_path: Path) -> PatchProposal:
        """Load a pending patch proposal from disk."""
        if not pending_patch_path.exists():
            raise FileNotFoundError("No pending patch found. Run 'sac edit' first.")

        data = json.loads(pending_patch_path.read_text(encoding="utf-8"))
        return PatchProposal(**data)
