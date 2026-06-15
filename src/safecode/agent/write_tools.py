"""Write-side native tools: edit_file, write_file (v4.21.0+, EXPERIMENTAL).

Both tools:
- Validate paths against the project root.
- Create a CheckpointMetadata record before any mutation (via PatchProposal shim).
- Consult ToolCallGate before executing.
- Have requires_approval=True (callers gate on approval state).
- Audit as tool_call_write events.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any
from uuid import uuid4

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.context.redactor import redact_secrets
from safecode.patch.applier import PatchApplyError, PatchApplier, PatchValidationError
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


def _validate_write_path(project_root: Path, raw_path: str) -> tuple[Path, str | None]:
    """Return (resolved_absolute, error_msg). error_msg is None on success."""
    candidate = Path(raw_path)
    absolute = candidate if candidate.is_absolute() else project_root / candidate
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return project_root, f"Path {raw_path!r} is outside the project root."
    return resolved, None


def _make_proposal(task: str, operation: str, file_path: str,
                   search: str | None, replace: str | None, content: str | None) -> PatchProposal:
    return PatchProposal(
        id=f"native-{uuid4().hex[:8]}",
        task=task,
        blocks=[PatchBlock(
            operation=operation,
            file_path=Path(file_path),
            search=search,
            replace=replace,
            content=content,
        )],
        created_at=utc_now_iso(),
        model="native_tool",
    )


def _compact_diff(old: str, new: str, path: str) -> str:
    """Return a short unified diff for display in StopForUser messages."""
    diff = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    ))
    return "".join(diff[:60])  # Cap at 60 diff lines for display


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

def _edit_file_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    raw_path: str = inp.get("path", "")
    old_string: str = inp.get("old_string", "")
    new_string: str = inp.get("new_string", "")
    description: str = inp.get("description", "edit_file")
    approved: bool = inp.get("_approved", False)

    if not raw_path:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error", error="Missing 'path'.")
    if old_string == "":
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error", error="'old_string' must be non-empty.")

    resolved, err = _validate_write_path(project_root, raw_path)
    if err:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="blocked", error=err)

    if not resolved.is_file():
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error",
                                error=f"File not found: {raw_path!r}")

    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error",
                                error=f"Read error: {type(exc).__name__}")

    count = content.count(old_string)
    if count == 0:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error",
                                error="'old_string' not found in file.")
    if count > 1:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error",
                                error=f"'old_string' matches {count} times — must be unique.")

    if not approved:
        diff_preview = _compact_diff(content, content.replace(old_string, new_string, 1), raw_path)
        return NativeToolResult(
            call_id=call_id,
            tool_name="edit_file",
            status="blocked",
            error="Approval required before edit_file executes.",
            metadata={"requires_approval": True, "diff_preview": diff_preview, "path": raw_path},
        )

    # Create checkpoint via PatchApplier (which uses CheckpointManager internally).
    proposal = _make_proposal(description, "update", raw_path, old_string, new_string, None)
    try:
        from safecode.checkpoint.manager import CheckpointManager
        checkpoint = CheckpointManager(project_root).create(proposal)
        applier = PatchApplier(project_root)
        applier.apply(proposal)
    except (PatchApplyError, PatchValidationError) as exc:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error", error=str(exc))
    except Exception as exc:
        return NativeToolResult(call_id=call_id, tool_name="edit_file", status="error",
                                error=f"Unexpected error: {type(exc).__name__}")

    return NativeToolResult(
        call_id=call_id,
        tool_name="edit_file",
        output=f"Edited {raw_path}",
        metadata={"checkpoint_id": checkpoint.checkpoint_id, "path": raw_path},
    )


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

def _write_file_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    raw_path: str = inp.get("path", "")
    content: str = inp.get("content", "")
    description: str = inp.get("description", "write_file")
    approved: bool = inp.get("_approved", False)

    if not raw_path:
        return NativeToolResult(call_id=call_id, tool_name="write_file", status="error", error="Missing 'path'.")

    resolved, err = _validate_write_path(project_root, raw_path)
    if err:
        return NativeToolResult(call_id=call_id, tool_name="write_file", status="blocked", error=err)

    # Refuse sensitive path writes.
    from safecode.agent.read_tools import _is_safe_file, SKIP_DIRS
    rel_parts = {p.lower() for p in resolved.relative_to(project_root.resolve()).parts}
    if rel_parts & SKIP_DIRS:
        return NativeToolResult(call_id=call_id, tool_name="write_file", status="blocked",
                                error=f"Path {raw_path!r} is inside a protected directory.")

    if not approved:
        old_content = resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        diff_preview = _compact_diff(old_content, content, raw_path)
        return NativeToolResult(
            call_id=call_id,
            tool_name="write_file",
            status="blocked",
            error="Approval required before write_file executes.",
            metadata={"requires_approval": True, "diff_preview": diff_preview, "path": raw_path},
        )

    operation = "update" if resolved.exists() else "create"
    proposal = _make_proposal(description, operation, raw_path,
                              search=resolved.read_text(encoding="utf-8") if resolved.exists() else None,
                              replace=content if operation == "update" else None,
                              content=content if operation == "create" else None)
    try:
        from safecode.checkpoint.manager import CheckpointManager
        checkpoint = CheckpointManager(project_root).create(proposal)
        applier = PatchApplier(project_root)
        applier.apply(proposal)
    except (PatchApplyError, PatchValidationError) as exc:
        return NativeToolResult(call_id=call_id, tool_name="write_file", status="error", error=str(exc))
    except Exception as exc:
        return NativeToolResult(call_id=call_id, tool_name="write_file", status="error",
                                error=f"Unexpected error: {type(exc).__name__}")

    return NativeToolResult(
        call_id=call_id,
        tool_name="write_file",
        output=f"{'Created' if operation == 'create' else 'Overwrote'} {raw_path}",
        metadata={"checkpoint_id": checkpoint.checkpoint_id, "path": raw_path, "operation": operation},
    )


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

EDIT_FILE_SPEC = NativeToolSpec(
    name="edit_file",
    description="Exact string replacement in one file. Fails if old_string is not found or not unique. Creates a checkpoint before apply.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project-relative file path."},
            "old_string": {"type": "string", "description": "Exact string to replace (must match exactly once)."},
            "new_string": {"type": "string", "description": "Replacement string."},
            "description": {"type": "string", "description": "Human-readable description of the edit."},
        },
        "required": ["path", "old_string", "new_string"],
    },
    requires_approval=True,
    audit_event_type="tool_call_write",
    experimental=False,  # Stable contract since v5.0.0
)

WRITE_FILE_SPEC = NativeToolSpec(
    name="write_file",
    description="Overwrite or create a file. Creates a checkpoint before apply. Refuses paths outside project root or in protected directories.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project-relative file path."},
            "content": {"type": "string", "description": "Full file content to write."},
            "description": {"type": "string", "description": "Human-readable description of the write."},
        },
        "required": ["path", "content"],
    },
    requires_approval=True,
    audit_event_type="tool_call_write",
    experimental=False,  # Stable contract since v5.0.0
)


def register_write_tools(dispatcher: NativeToolDispatcher, project_root: Path,
                         *, approved: bool = False) -> None:
    """Register write tools on a dispatcher, injecting project_root and approval state."""

    def make_handler(fn):
        def _handler(call_id: str, inp: dict) -> NativeToolResult:
            return fn(call_id, {"_project_root": str(project_root), "_approved": approved, **inp})
        return _handler

    dispatcher.register(EDIT_FILE_SPEC, make_handler(_edit_file_handler))
    dispatcher.register(WRITE_FILE_SPEC, make_handler(_write_file_handler))
