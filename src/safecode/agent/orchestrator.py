"""Coordinate context collection, LLM responses, patch handling, and audit logs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


def _extract_seed_files(task: str, project_root: Path) -> list[str]:
    """Extract mentioned file paths from a task description for import-graph seeding (v5.3.0).

    Scans the task text for path-like tokens and returns those that actually exist
    within the project root. Returns at most 3 seed files.
    """
    root = project_root.resolve()
    # Match path-like tokens: word chars, dots, slashes (but not URLs)
    candidates = re.findall(r'(?<![:/])(?:[\w./]+\.(?:py|ts|tsx|js|jsx|go|rs|rb|java|kt))', task)
    result: list[str] = []
    for candidate in candidates:
        path = root / candidate
        try:
            path.resolve().relative_to(root)
            if path.is_file():
                result.append(candidate)
        except (ValueError, OSError):
            pass
        if len(result) >= 3:
            break
    return result


_SMALL_FILE_LIMIT = 8_000   # bytes; skip files larger than this
_MAX_INJECTED_FILES = 20    # cap to avoid blowing the context budget
_PATCH_RETRY_FILE_LIMIT = 16_000
_PATCH_RETRY_MAX_FILES = 8

def _inject_all_small_files(context: dict, project_root: Path) -> None:
    """Fallback: when keyword-based context selection found nothing, include all small
    project files so the model can see their contents without issuing read tool calls.

    Only plain-text files under _SMALL_FILE_LIMIT bytes are added.  Binary and
    sensitive paths are skipped.  Results are stored in context["selected_context"]
    to match the shape the LLM prompt already serialises.
    """
    _SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".sac"}
    _SKIP_EXTS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".jpg",
                  ".png", ".gif", ".pdf", ".zip", ".tar", ".gz"}
    snippets: dict[str, str] = {}
    sources: list[dict] = []
    root = project_root.resolve()
    for path in sorted(root.rglob("*")):
        if len(snippets) >= _MAX_INJECTED_FILES:
            break
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in _SKIP_EXTS:
            continue
        try:
            size = path.stat().st_size
            if size > _SMALL_FILE_LIMIT:
                continue
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            snippets[rel] = text
            sources.append({"path": rel, "score": 0, "reason": "fallback: all small files"})
        except OSError:
            continue
    sc = context.setdefault("selected_context", {})
    if isinstance(sc, dict):
        sc.setdefault("snippets", {}).update(snippets)
        sc.setdefault("sources", []).extend(sources)


def _collect_patch_retry_files(proposal: "PatchProposal", project_root: Path) -> dict[str, str]:
    """Collect exact current contents for files touched by a failed patch proposal."""
    files: dict[str, str] = {}
    root = project_root.resolve()
    for block in proposal.blocks:
        if len(files) >= _PATCH_RETRY_MAX_FILES:
            break
        try:
            path = (root / block.file_path).resolve()
            path.relative_to(root)
            if not path.is_file() or path.stat().st_size > _PATCH_RETRY_FILE_LIMIT:
                continue
            files[block.file_path.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return files


def _build_patch_retry_context(
    context: dict,
    proposal: "PatchProposal",
    project_root: Path,
    exc: Exception,
) -> dict:
    """Add validation feedback and exact file contents for one patch regeneration attempt."""
    retry_context = dict(context)
    retry_context["patch_validation_retry"] = {
        "reason": str(exc),
        "instruction": (
            "The previous patch failed validation because a SEARCH block did not "
            "match the file exactly. Regenerate the full SafeCode patch once. "
            "Copy SEARCH text verbatim from current_files and keep changes minimal."
        ),
        "current_files": _collect_patch_retry_files(proposal, project_root),
        "previous_patch": {
            "files": [block.file_path.as_posix() for block in proposal.blocks],
            "block_count": len(proposal.blocks),
        },
    }
    return retry_context


def _build_patch_parse_retry_context(context: dict, patch_text: str, exc: Exception) -> dict:
    """Add parse feedback for one patch regeneration attempt."""
    retry_context = dict(context)
    retry_context["patch_parse_retry"] = {
        "reason": str(exc),
        "instruction": (
            "The previous response could not be parsed as a SafeCode patch. "
            "Regenerate the full patch once using exactly one *** Begin Patch / "
            "*** End Patch envelope, at least one *** Update File section, and "
            "non-empty SEARCH/REPLACE blocks copied from the current context."
        ),
        "previous_patch_text": patch_text[:4000],
    }
    return retry_context

from safecode.agent.planner import DiffPlanner, DiffScopeResult
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.checkpoint.manager import CheckpointManager
from safecode.checkpoint.models import CheckpointMetadata
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.core.failure_category import FailureCategory, category_for_exception
from safecode.context.collector import ContextCollector
from safecode.hooks.runner import HookRunner, HookRunSummary
from safecode.llm.factory import create_llm_client
from safecode.llm.stream import StreamChunk, SupportsStreaming
from safecode.patch.applier import PatchApplier
from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchProposal
from safecode.patch.parser import PatchParseError, PatchParser
from safecode.patch.validator import PatchValidationError, PatchValidator
from safecode.trace.events import TraceLogger
from safecode.utils.time import utc_now_iso
from safecode.metrics.writer import make_metrics_writer
from safecode.logs.runtime import RuntimeLogger


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

    def __init__(
        self,
        project_root: Path,
        llm_client: object | None = None,
        config: SafeCodeConfig | None = None,
        on_step: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.on_step = on_step
        self.context_collector = ContextCollector(project_root, self.config)
        self.llm_client = llm_client if llm_client is not None else create_llm_client(self.config)
        self.audit_logger = AuditLogger(project_root, self.config)
        self.trace_logger = TraceLogger(project_root)
        self._metrics = make_metrics_writer(project_root, session_id="orchestrator")

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

    def ask_stream(self, question: str) -> Iterator[StreamChunk]:
        """Stream a read-only answer token-by-token. Non-streaming fallback if unsupported."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "ask_stream.start", question)
        context = self.context_collector.collect()
        messages = [
            {"role": "system", "content": "You are SafeCode Agent. Answer the question about the current project."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ]
        if isinstance(self.llm_client, SupportsStreaming):
            raw_chunks = self.llm_client.stream_chat(messages)
            full_text = ""
            for chunk in raw_chunks:
                redacted_delta = redact_secrets(chunk.delta)
                full_text += redacted_delta
                yield StreamChunk(delta=redacted_delta, finish_reason=chunk.finish_reason)
            self.trace_logger.write(trace_id, "ask_stream.completed", "streamed read-only answer")
            self.audit_logger.write(
                AuditEvent(
                    type="ask_completed",
                    timestamp=utc_now_iso(),
                    message=question,
                    trace_id=trace_id,
                )
            )
        else:
            answer = self.llm_client.ask(question, context)
            content = getattr(answer, "content", None) or str(answer)
            redacted = redact_secrets(str(content))
            self.trace_logger.write(trace_id, "ask_stream.completed", "batch fallback")
            self.audit_logger.write(
                AuditEvent(
                    type="ask_completed",
                    timestamp=utc_now_iso(),
                    message=question,
                    trace_id=trace_id,
                )
            )
            yield StreamChunk(delta=redacted, finish_reason="stop")

    def edit(self, task: str) -> EditResult:
        """Generate and store a pending patch proposal."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "edit.start", task)
        self._metrics.record_step_start(0, tool_intent="edit")

        planner = DiffPlanner()
        diff_plan = planner.predict(task)

        # v5.3.0: extract seed files from task description for import-graph seeding
        seed_files = _extract_seed_files(task, self.project_root)
        context = self.context_collector.collect(
            query=task,
            seed_files=seed_files if seed_files else None,
            include_git_context=True,
            include_diagnostics=True,
        )
        # When keyword matching found no snippets, include all small project files so
        # the model has file contents and doesn't need to issue read tool calls first.
        sc = context.get("selected_context", {})
        _context_fallback_used = not bool(sc.get("snippets"))
        if _context_fallback_used:
            _inject_all_small_files(context, self.project_root)
        patch_retry_needed = False
        tool_calls = 1
        input_tokens = 0
        output_tokens = 0
        try:
            patch_response = self.llm_client.propose_patch(task, context)
            input_tokens += getattr(patch_response, "input_tokens", 0)
            output_tokens += getattr(patch_response, "output_tokens", 0)
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "model patch proposal failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=category_for_exception(exc),
            )
            raise
        try:
            proposal = PatchParser().parse(patch_response.patch_text, task=task)
        except PatchParseError as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "patch parse failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_PARSE_FAILED.value,
            )
            retry_context = _build_patch_parse_retry_context(context, patch_response.patch_text, exc)
            retry_task = (
                f"{task}\n\n"
                "Retry the patch proposal once. The previous response could not be parsed: "
                f"{exc}. Output only a valid SafeCode SEARCH/REPLACE patch."
            )
            patch_retry_needed = True
            tool_calls += 1
            try:
                patch_response = self.llm_client.propose_patch(retry_task, retry_context)
                input_tokens += getattr(patch_response, "input_tokens", 0)
                output_tokens += getattr(patch_response, "output_tokens", 0)
                proposal = PatchParser().parse(patch_response.patch_text, task=task)
            except Exception as retry_exc:
                RuntimeLogger(self.project_root, self.config).error(
                    "agent.orchestrator",
                    "patch parse retry failed",
                    exc=retry_exc,
                    trace_id=trace_id,
                    failure_category=category_for_exception(retry_exc),
                )
                raise retry_exc from exc
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "patch parse failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_PARSE_FAILED.value,
            )
            raise

        scope_result = planner.compare(diff_plan, proposal)

        try:
            PatchValidator(self.project_root).validate(proposal)
        except PatchValidationError as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "patch validation failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value,
            )
            retry_context = _build_patch_retry_context(context, proposal, self.project_root, exc)
            retry_task = (
                f"{task}\n\n"
                "Retry the patch proposal once. The previous patch failed validation: "
                f"{exc}. Use patch_validation_retry.current_files for exact SEARCH text."
            )
            patch_retry_needed = True
            tool_calls += 1
            try:
                patch_response = self.llm_client.propose_patch(retry_task, retry_context)
                input_tokens += getattr(patch_response, "input_tokens", 0)
                output_tokens += getattr(patch_response, "output_tokens", 0)
                proposal = PatchParser().parse(patch_response.patch_text, task=task)
                scope_result = planner.compare(diff_plan, proposal)
                PatchValidator(self.project_root).validate(proposal)
            except Exception as retry_exc:
                RuntimeLogger(self.project_root, self.config).error(
                    "agent.orchestrator",
                    "patch validation retry failed",
                    exc=retry_exc,
                    trace_id=trace_id,
                    failure_category=category_for_exception(retry_exc),
                )
                raise retry_exc from exc
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "patch validation failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value,
            )
            raise
        diff_text = build_unified_diff(self.project_root, proposal)
        pending_patch_path = self._save_pending_patch(proposal)
        self.trace_logger.write(trace_id, "edit.patch_saved", proposal.id)

        audit_metadata: dict[str, str] = {"scope_status": scope_result.status}
        if scope_result.warning:
            audit_metadata["scope_warning"] = scope_result.warning
        if patch_retry_needed:
            audit_metadata["patch_retry_needed"] = "true"

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
        self._metrics.record_pending_patch(0, patch_response.patch_text)
        self._metrics.record_step_end(0, tool_intent="edit")
        if self.on_step:
            self.on_step(
                {
                    "tool_intent": "edit",
                    "tool_calls": tool_calls,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "context_fallback_used": _context_fallback_used,
                    "patch_retry_needed": patch_retry_needed,
                }
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

        try:
            PatchValidator(self.project_root).validate(proposal)
            diff_text = build_unified_diff(self.project_root, proposal)
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "apply preview failed",
                exc=exc,
                failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value,
            )
            raise
        return ApplyPreview(
            proposal=proposal,
            diff_text=diff_text,
            pending_patch_path=pending_patch_path,
        )

    def apply(self, proposal: PatchProposal) -> ApplyResult:
        """Checkpoint and apply a previously previewed pending patch."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "apply.start", proposal.id)
        try:
            PatchValidator(self.project_root).validate(proposal)
            self._guard_dirty_patch_targets(proposal)
            checkpoint = CheckpointManager(self.project_root).create(proposal)
            self.trace_logger.write(trace_id, "apply.checkpoint_created", checkpoint.checkpoint_id)
            PatchApplier(self.project_root).apply(proposal)
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "patch apply failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value,
            )
            raise
        hook_runner = HookRunner(self.project_root, self.config)
        hook_runner.run_after_edit()
        hooks = hook_runner.run_after_apply()
        self._pending_patch_path().unlink(missing_ok=True)
        self.trace_logger.write(trace_id, "apply.completed", proposal.id)

        files = [block.file_path.as_posix() for block in proposal.blocks]

        # v6.30: capture cross-session workspace memory after a successful apply.
        self._capture_workspace_memory(proposal.task, files)

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

    def _capture_workspace_memory(self, task: str, files: list[str]) -> None:
        """Record what the agent learned from this apply into cross-session memory (v6.30).

        Best-effort: failures here must never block the apply flow.
        """
        try:
            from safecode.memory.workspace_memory import WorkspaceMemoryStore

            store = WorkspaceMemoryStore(self.project_root)
            file_stems = {Path(f).stem for f in files}
            for stem in sorted(file_stems)[:5]:
                store.record(
                    key=f"fix:{stem}",
                    value=task[:200],
                    source="agent_observed",
                )
        except Exception:
            pass

    def _guard_dirty_patch_targets(self, proposal: PatchProposal) -> None:
        """Refuse to apply over dirty target files in git worktrees."""
        try:
            from safecode.git.local import changed_files, is_git_repo

            if not is_git_repo(self.project_root):
                return
            targets = {block.file_path.as_posix() for block in proposal.blocks}
            dirty_targets = sorted(set(changed_files(self.project_root)) & targets)
            if dirty_targets:
                joined = ", ".join(dirty_targets)
                raise PatchValidationError(
                    "Dirty target files would be overwritten by this patch: "
                    f"{joined}. Commit, stash, or revert those changes first."
                )
        except PatchValidationError:
            raise
        except Exception:
            return

    def rollback_last(self) -> RollbackResult:
        """Restore the latest checkpoint and audit the rollback."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "rollback.start", "latest")
        try:
            checkpoint = CheckpointManager(self.project_root).rollback_last()
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "rollback failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value,
            )
            raise
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

    def rollback_checkpoint(self, checkpoint_id: str) -> RollbackResult:
        """Restore a specific checkpoint by ID."""
        trace_id = self.trace_logger.new_trace_id()
        self.trace_logger.write(trace_id, "rollback.start", checkpoint_id)
        try:
            checkpoint = CheckpointManager(self.project_root).rollback_by_checkpoint_id(checkpoint_id)
        except Exception as exc:
            RuntimeLogger(self.project_root, self.config).error(
                "agent.orchestrator",
                "rollback failed",
                exc=exc,
                trace_id=trace_id,
                failure_category=FailureCategory.PATCH_APPLY_CONFLICT.value,
            )
            raise
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

    def list_checkpoints(self) -> list[CheckpointMetadata]:
        """List all available checkpoints, newest first."""
        return CheckpointManager(self.project_root).list_checkpoints()

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
