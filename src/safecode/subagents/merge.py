"""Subagent merge review: create a pending patch from completed subagent results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.patch.validator import PatchValidator
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.subagents.task import SubagentTask, SubagentTaskStore, validate_task_id
from safecode.utils.time import utc_now_iso

MERGE_MARKER = "<!-- SAFECODE:SUBAGENT_REVIEW -->"


@dataclass(frozen=True)
class SubagentMergeResult:
    """Result of a subagent merge review proposal."""

    proposal: PatchProposal
    diff_text: str
    pending_path: Path


class SubagentMergeReviewer:
    """Read completed subagent results and create a pending patch proposal."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = config or SafeCodeConfig.load(project_root)
        self.store = SubagentTaskStore(project_root)
        self.audit_logger = AuditLogger(project_root, self.config)
        self.validator = PatchValidator(project_root)
        self.filesystem = FilesystemBoundary(project_root, self.config)

    def propose(self, task_ids: list[str], target: str) -> SubagentMergeResult:
        """Create a pending patch proposal from completed subagent results."""
        try:
            return self._propose(task_ids, target)
        except Exception as exc:
            self._audit("subagent_merge_blocked", None, f"Merge review blocked: {exc}", task_ids, target)
            raise

    def _propose(self, task_ids: list[str], target: str) -> SubagentMergeResult:
        """Internal merge proposal implementation."""
        if not task_ids:
            raise ValueError("At least one task ID is required.")

        pending_path = self.project_root / self.config.sac_dir / "pending_patch.json"
        if pending_path.exists():
            raise FileExistsError(
                "A pending patch already exists. Apply or discard it before creating a new merge review."
            )

        target_path = self._resolve_target(target)
        tasks = self._load_completed_tasks(task_ids)
        results_content = self._read_result_files(tasks)
        redacted_content = redact_secrets(results_content)
        review_content = self._build_review(tasks, redacted_content)

        proposal = PatchProposal(
            id=f"merge_{task_ids[0][:8]}",
            task=f"Merge subagent review for {len(tasks)} task(s)",
            blocks=[
                PatchBlock(
                    operation="update",
                    file_path=Path(target),
                    search=MERGE_MARKER,
                    replace=MERGE_MARKER + "\n\n" + review_content,
                )
            ],
            created_at=utc_now_iso(),
            model="merge-review",
        )

        self.validator.validate(proposal)
        diff_text = build_unified_diff(self.project_root, proposal)
        self._save_pending_patch(proposal)
        self._audit(
            "subagent_merge_proposed",
            None,
            f"Merge review proposal created for {len(task_ids)} task(s).",
            task_ids,
            target,
        )

        return SubagentMergeResult(proposal=proposal, diff_text=diff_text, pending_path=pending_path)

    def _resolve_target(self, target: str) -> Path:
        target_path = (self.project_root / target).resolve()
        try:
            self.filesystem.validate(target_path)
        except PermissionError as exc:
            raise PermissionError(str(exc)) from exc
        if not target_path.exists():
            raise FileNotFoundError(f"Target file does not exist: {target}")
        if not target_path.is_file():
            raise ValueError(f"Target path is not a file: {target}")
        content = target_path.read_text(encoding="utf-8")
        if MERGE_MARKER not in content:
            raise ValueError(
                f"Target file must contain the merge marker: {MERGE_MARKER}. "
                "Add this marker to your review file first."
            )
        return target_path

    def _load_completed_tasks(self, task_ids: list[str]) -> list[SubagentTask]:
        tasks: list[SubagentTask] = []
        for task_id in task_ids:
            validate_task_id(task_id)
            task = self.store.load(task_id)
            if task is None:
                raise FileNotFoundError(f"Subagent task not found: {task_id}")
            if not task.readonly:
                raise PermissionError(f"Task {task_id} is not read-only and cannot be merged.")
            if task.status != "completed":
                raise ValueError(f"Task {task_id} is not completed (status: {task.status}).")
            if task.result_path is None:
                raise FileNotFoundError(f"Task {task_id} has no result file path.")
            tasks.append(task)
        return tasks

    def _read_result_files(self, tasks: list[SubagentTask]) -> str:
        parts: list[str] = []
        for task in tasks:
            result_path = Path(task.result_path) if task.result_path else None
            if result_path is None:
                raise FileNotFoundError(f"Task {task.id} has no result file path.")
            resolved = result_path.resolve()
            subagents_root = (self.project_root / self.config.sac_dir / "subagents").resolve()
            try:
                resolved.relative_to(subagents_root)
            except ValueError:
                raise PermissionError(
                    f"Result file for task {task.id} is outside .sac/subagents/ and cannot be read."
                )
            if not resolved.exists():
                raise FileNotFoundError(f"Result file missing for task {task.id}: {result_path}")
            content = resolved.read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError(f"Result file for task {task.id} is empty.")
            parts.append(content)
        return "\n\n---\n\n".join(parts)

    def _build_review(self, tasks: list[SubagentTask], content: str) -> str:
        task_list = "\n".join(f"- {task.id}: {task.title}" for task in tasks)
        return (
            f"## Subagent Merge Review\n\n"
            f"**Generated**: {utc_now_iso()}\n\n"
            f"### Tasks Reviewed\n\n"
            f"{task_list}\n\n"
            f"### Findings\n\n"
            f"{content}\n"
        )

    def _save_pending_patch(self, proposal: PatchProposal) -> Path:
        pending_path = self.project_root / self.config.sac_dir / "pending_patch.json"
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        return pending_path

    def _audit(
        self,
        event_type: str,
        task_id: str | None,
        message: str,
        task_ids: list[str] | None = None,
        target: str | None = None,
    ) -> None:
        metadata: dict[str, str] = {}
        if task_id:
            metadata["task_id"] = task_id
        if task_ids:
            metadata["task_ids"] = ",".join(task_ids)
        if target:
            metadata["target"] = target
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status="success" if "proposed" in event_type else "blocked",
                message=message,
                metadata=metadata,
            )
        )
