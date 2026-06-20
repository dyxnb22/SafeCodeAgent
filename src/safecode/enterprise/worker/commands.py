"""Run command handlers for the Team Server API (v2.1.5-T1)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from safecode.enterprise.persistence.run_artifact_lock import run_artifact_lock
from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.worker.models import RunAccepted
from safecode.enterprise.worker.queue import (
    CommandQueue,
    IdempotencyConflictError,
    LocalCommandQueue,
    ensure_command_enqueued,
    validate_command_match,
)
from safecode.enterprise.worker.status import is_terminal
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.exceptions import (
    CheckpointCorruptedError,
    CheckpointNotFoundError,
    UnsupportedWorkflowTaskError,
)
from safecode.enterprise.workflow.ids import generate_run_id, validate_run_id
from safecode.enterprise.workflow.orchestrator import (
    build_initial_state,
    ensure_workflow_task_executable,
    utc_now_iso,
)
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

if TYPE_CHECKING:
    from safecode.enterprise.persistence.local_backend import LocalBackend
    from safecode.enterprise.persistence.postgres.backend import PostgresBackend

    PersistenceBackend = LocalBackend | PostgresBackend
else:
    PersistenceBackend = object


def command_queue_for(backend: PersistenceBackend) -> CommandQueue:
    queue = getattr(backend, "commands", None)
    if queue is not None:
        return queue
    sac_root = getattr(backend, "sac_root", None)
    if sac_root is not None:
        return LocalCommandQueue(sac_root)
    raise TypeError("backend does not expose a command queue")


def _load_status(backend: PersistenceBackend, *, tenant_id: str, run_id: str) -> str:
    checkpoint = backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
    return checkpoint.state.status.value


def _artifacts_root(backend: PersistenceBackend) -> Path:
    root = getattr(backend, "sac_root", None)
    if root is None:
        root = getattr(backend, "artifacts_root", None)
    if root is None:
        raise TypeError("backend does not expose an artifact root")
    return Path(root)


def _ensure_start_checkpoint(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    run_id: str,
    task_type: TaskType,
    input_ref: str,
    subject: RBACSubject,
    project_root: Path,
) -> RunCheckpoint:
    """Create or recover the claimed start checkpoint exactly once."""
    with run_artifact_lock(
        _artifacts_root(backend),
        tenant_id=tenant_id,
        run_id=run_id,
    ):
        try:
            checkpoint = backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
        except CheckpointNotFoundError:
            state = build_initial_state(
                task_type=task_type,
                input_ref=input_ref,
                actor_id=subject.actor_id,
                repo_root=project_root,
                run_id=run_id,
                tenant_id=tenant_id,
            )
            checkpoint = RunCheckpoint(
                schema_version=CHECKPOINT_SCHEMA_VERSION,
                run_id=run_id,
                completed_nodes=[],
                next_node="classify_request",
                state=state,
            )
            backend.runs.save_checkpoint(tenant_id=tenant_id, checkpoint=checkpoint)
        state = checkpoint.state
        if (
            state.task_type != task_type
            or state.request.input_ref != input_ref
            or state.actor_id != subject.actor_id
        ):
            raise IdempotencyConflictError(
                "stored start checkpoint does not match the idempotent command binding"
            )
        return checkpoint


def _save_cancelled(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    run_id: str,
) -> str:
    checkpoint = backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
    if is_terminal(checkpoint.state.status):
        return checkpoint.state.status.value
    updated = checkpoint.state.model_copy(
        update={
            "status": WorkflowStatus.cancelled,
            "updated_at": utc_now_iso(),
        }
    )
    backend.runs.save_checkpoint(
        tenant_id=tenant_id,
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=run_id,
            completed_nodes=list(checkpoint.completed_nodes),
            next_node=checkpoint.next_node,
            state=updated,
        ),
    )
    return WorkflowStatus.cancelled.value


def start_run(
    backend: PersistenceBackend,
    queue: CommandQueue,
    *,
    tenant_id: str,
    idempotency_key: str,
    task_type: str,
    input_ref: str | None,
    subject: RBACSubject,
    project_root: Path,
) -> RunAccepted:
    tenant = validate_tenant_id(tenant_id)
    key = idempotency_key.strip()
    try:
        parsed_task = TaskType(task_type)
    except ValueError as exc:
        raise ValueError(f"unsupported task_type: {task_type!r}") from exc
    if not input_ref:
        raise ValueError("input_ref is required")
    try:
        ensure_workflow_task_executable(parsed_task)
    except UnsupportedWorkflowTaskError as exc:
        raise ValueError(str(exc)) from exc
    payload = {
        "task_type": task_type,
        "input_ref": input_ref,
        "actor_id": subject.actor_id,
    }
    proposed_run_id = validate_run_id(generate_run_id())
    record = queue.record_command(
        tenant_id=tenant,
        idempotency_key=key,
        command="start",
        run_id=proposed_run_id,
        payload=payload,
    )
    validate_command_match(
        record,
        command="start",
        run_id=record.run_id,
        payload=payload,
    )
    checkpoint = _ensure_start_checkpoint(
        backend,
        tenant_id=tenant,
        run_id=record.run_id,
        task_type=parsed_task,
        input_ref=input_ref,
        subject=subject,
        project_root=project_root,
    )
    queue.enqueue_command_job(record)
    return RunAccepted(
        run_id=record.run_id,
        status=checkpoint.state.status.value,
        status_url=f"/v2/runs/{record.run_id}?tenant_id={tenant}",
    )


def resume_run(
    backend: PersistenceBackend,
    queue: CommandQueue,
    *,
    tenant_id: str,
    idempotency_key: str,
    run_id: str,
) -> RunAccepted:
    tenant = validate_tenant_id(tenant_id)
    validate_run_id(run_id)
    key = idempotency_key.strip()
    existing = queue.get_command(tenant_id=tenant, idempotency_key=key)
    if existing is not None:
        validate_command_match(
            existing,
            command="resume",
            run_id=run_id,
        )
        queue.enqueue_command_job(existing)
        status = _load_status(backend, tenant_id=tenant, run_id=existing.run_id)
        return RunAccepted(
            run_id=existing.run_id,
            status=status,
            status_url=f"/v2/runs/{existing.run_id}?tenant_id={tenant}",
        )
    backend.runs.load_checkpoint(tenant_id=tenant, run_id=run_id)
    ensure_command_enqueued(
        queue,
        tenant_id=tenant,
        idempotency_key=key,
        command="resume",
        run_id=run_id,
    )
    status = _load_status(backend, tenant_id=tenant, run_id=run_id)
    return RunAccepted(
        run_id=run_id,
        status=status,
        status_url=f"/v2/runs/{run_id}?tenant_id={tenant}",
    )


def cancel_run(
    backend: PersistenceBackend,
    queue: CommandQueue,
    *,
    tenant_id: str,
    idempotency_key: str,
    run_id: str,
) -> RunAccepted:
    tenant = validate_tenant_id(tenant_id)
    validate_run_id(run_id)
    key = idempotency_key.strip()
    existing = queue.get_command(tenant_id=tenant, idempotency_key=key)
    if existing is not None:
        validate_command_match(
            existing,
            command="cancel",
            run_id=run_id,
        )
        queue.enqueue_command_job(existing)
        status = _load_status(backend, tenant_id=tenant, run_id=existing.run_id)
        return RunAccepted(
            run_id=existing.run_id,
            status=status,
            status_url=f"/v2/runs/{existing.run_id}?tenant_id={tenant}",
        )
    status = _save_cancelled(backend, tenant_id=tenant, run_id=run_id)
    ensure_command_enqueued(
        queue,
        tenant_id=tenant,
        idempotency_key=key,
        command="cancel",
        run_id=run_id,
    )
    return RunAccepted(
        run_id=run_id,
        status=status,
        status_url=f"/v2/runs/{run_id}?tenant_id={tenant}",
    )


def resolve_existing_command(
    backend: PersistenceBackend,
    queue: CommandQueue,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> RunAccepted | None:
    record = queue.get_command(
        tenant_id=validate_tenant_id(tenant_id),
        idempotency_key=idempotency_key.strip(),
    )
    if record is None:
        return None
    queue.enqueue_command_job(record)
    try:
        status = _load_status(backend, tenant_id=record.tenant_id, run_id=record.run_id)
    except CheckpointCorruptedError:
        status = WorkflowStatus.pending.value
    return RunAccepted(
        run_id=record.run_id,
        status=status,
        status_url=f"/v2/runs/{record.run_id}?tenant_id={record.tenant_id}",
    )
