"""Coordinate context collection, LLM responses, patch handling, and audit logs."""

import json
from dataclasses import dataclass
from pathlib import Path

from safecode.agent.planner import DiffPlanner, DiffScopeResult
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.checkpoint.manager import CheckpointManager
from safecode.checkpoint.models import CheckpointMetadata
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.hooks.runner import HookRunner, HookRunSummary
from safecode.llm.factory import create_llm_client
from safecode.patch.applier import PatchApplier
from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchProposal
from safecode.patch.parser import PatchParser
from safecode.patch.validator import PatchValidator
from safecode.trace.events import TraceLogger
from safecode.utils.time import utc_now_iso


@dataclass
class EditResult:
    """Result returned by sac edit before any file is modified."""

    proposal: PatchProposal
    diff_text: str
    pending_patch_path: Path
    scope_result: DiffScopeResult | None = None


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
    hooks: HookRunSummary | None = None


@dataclass
class RollbackResult:
    """Result after restoring the latest checkpoint."""

    checkpoint: CheckpointMetadata
    files: list[str]


class AgentOrchestrator:
    """High-level workflow entrypoint for v0.1 commands."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.config = SafeCodeConfig.load(project_root)
        self.context_collector = ContextCollector(project_root, self.config)
        self.llm_client = create_llm_client(self.config)
        self.audit_logger = AuditLogger(project_root, self.config)
        self.trace_logger = TraceLogger(project_root)

    def ask(self, question: str) -> str:
        """Return a read-only answer about the current project."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "ask.start", question)
        context = self.context_collector.collect()
        answer = self.llm_client.ask(question, context)
        self.trace_logger.write(trace_id, "ask.completed", "answered read-only question")
        self.audit_logger.write(
            AuditEvent(
                type="ask_completed",
                timestamp=utc_now_iso(),
                message=question,
                trace_id=trace_id,
            )
        )
        return answer.content

    def edit(self, task: str) -> EditResult:
        """Generate and store a pending patch proposal."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "edit.start", task)

        planner = DiffPlanner()
        diff_plan = planner.predict(task)

        context = self.context_collector.collect()
        patch_response = self.llm_client.propose_patch(task, context)
        proposal = PatchParser().parse(patch_response.patch_text, task=task)

        scope_result = planner.compare(diff_plan, proposal)

        PatchValidator(self.project_root).validate(proposal)
        diff_text = build_unified_diff(self.project_root, proposal)
        pending_patch_path = self._save_pending_patch(proposal)
        self.trace_logger.write(trace_id, "edit.patch_saved", proposal.id)

        audit_metadata: dict[str, str] = {"scope_status": scope_result.status}
        if scope_result.warning:
            audit_metadata["scope_warning"] = scope_result.warning

        self.audit_logger.write(
            AuditEvent(
                type="patch_proposed",
                timestamp=utc_now_iso(),
                patch_id=proposal.id,
                files=[block.file_path.as_posix() for block in proposal.blocks],
                message=task,
                trace_id=trace_id,
                metadata=audit_metadata,
            )
        )
        return EditResult(
            proposal=proposal,
            diff_text=diff_text,
            pending_patch_path=pending_patch_path,
            scope_result=scope_result,
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
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "apply.start", proposal.id)
        PatchValidator(self.project_root).validate(proposal)
        checkpoint = CheckpointManager(self.project_root).create(proposal)
        self.trace_logger.write(trace_id, "apply.checkpoint_created", checkpoint.checkpoint_id)
        PatchApplier(self.project_root).apply(proposal)
        hooks = HookRunner(self.project_root, self.config).run_after_apply()
        self._pending_patch_path().unlink(missing_ok=True)
        self.trace_logger.write(trace_id, "apply.completed", proposal.id)

        files = [block.file_path.as_posix() for block in proposal.blocks]
        self.audit_logger.write(
            AuditEvent(
                type="checkpoint_created",
                timestamp=utc_now_iso(),
                patch_id=proposal.id,
                checkpoint_id=checkpoint.checkpoint_id,
                files=files,
                message=proposal.task,
                trace_id=trace_id,
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
                trace_id=trace_id,
            )
        )
        return ApplyResult(proposal=proposal, checkpoint=checkpoint, files=files, hooks=hooks)

    def rollback_last(self) -> RollbackResult:
        """Restore the latest checkpoint and audit the rollback."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "rollback.start", "latest")
        checkpoint = CheckpointManager(self.project_root).rollback_last()
        files = [operation.path for operation in checkpoint.file_operations]
        self.trace_logger.write(trace_id, "rollback.completed", checkpoint.checkpoint_id)
        self.audit_logger.write(
            AuditEvent(
                type="rollback_completed",
                timestamp=utc_now_iso(),
                patch_id=checkpoint.patch_id,
                checkpoint_id=checkpoint.checkpoint_id,
                files=files,
                message=checkpoint.task,
                trace_id=trace_id,
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
