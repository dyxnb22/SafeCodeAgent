"""TaskState Pydantic model for per-task sidecar files (experimental, v4.1+).

Each task sidecar lives at .sac/tasks/<task_id>.json and references stable
artifacts (pending patch id, audit trace ids) without changing their schemas.
payload_version=1; writes with payload_version > 1 are refused (fail closed).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from safecode.utils.time import utc_now_iso

_TASK_ID_MAX_LEN = 39
_SUPPORTED_PAYLOAD_VERSION = 1


class TaskCommand(BaseModel):
    """One recorded last_command entry."""

    command: str
    exit_code: int | None = None
    timestamp: str = Field(default_factory=utc_now_iso)


class TaskIteration(BaseModel):
    """One iteration record appended when edit/fix/apply occurs."""

    iteration_index: int
    event: str  # e.g. "edit", "fix", "apply", "rollback", "run"
    mode: str | None = None
    test_command: str | None = None
    suite: str | None = None
    test_exit_code: int | None = None
    exit_code: int | None = None
    failure_tail_sha256: str | None = None
    tail_hash: str | None = None
    pending_patch_id: str | None = None
    pending_patch_path: str | None = None
    status: str | None = None
    audit_trace_id: str | None = None
    timestamp: str = Field(default_factory=utc_now_iso)
    created_at: str = Field(default_factory=utc_now_iso)


class TaskState(BaseModel):
    """Sidecar state for one user task (experimental)."""

    task_id: str
    goal: str
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    status: Literal["open", "applied", "interrupted", "closed"] = "open"
    pending_patch_id: str | None = None
    session_id: str | None = None
    audit_trace_ids: list[str] = Field(default_factory=list)
    iterations: list[TaskIteration] = Field(default_factory=list)
    last_command: TaskCommand | None = None
    payload_version: int = _SUPPORTED_PAYLOAD_VERSION

    def next_iteration_index(self) -> int:
        """Return the next iteration index (len of existing iterations)."""
        return len(self.iterations)

    @classmethod
    def supported_payload_version(cls) -> int:
        return _SUPPORTED_PAYLOAD_VERSION
