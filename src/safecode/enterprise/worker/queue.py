"""Local command queue and shared queue protocol (v2.1.5-T1)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.worker.models import QueueJob, RunCommandKind, RunCommandRecord


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different command."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_idempotency_key(key: str) -> str:
    normalized = key.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise ValueError("idempotency key must be between 8 and 128 characters")
    return normalized


def _job_id() -> str:
    return f"job-{secrets.token_hex(8)}"


@runtime_checkable
class CommandQueue(Protocol):
    def get_command(
        self, *, tenant_id: str, idempotency_key: str
    ) -> RunCommandRecord | None: ...

    def record_command(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        command: RunCommandKind,
        run_id: str,
        payload: dict[str, str] | None = None,
    ) -> RunCommandRecord: ...

    def enqueue_job(
        self,
        *,
        tenant_id: str,
        run_id: str,
        command: RunCommandKind,
        payload: dict[str, str] | None = None,
    ) -> QueueJob: ...

    def poll_pending_job(self) -> QueueJob | None: ...

    def complete_job(self, job_id: str) -> None: ...

    def fail_job(self, job_id: str, *, message: str) -> None: ...


def _commands_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "worker" / "run_commands"


def _queue_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "worker" / "queue"


def _command_path(sac_root: Path, tenant_id: str, idempotency_key: str) -> Path:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    return _commands_root(sac_root) / validate_tenant_id(tenant_id) / f"{digest}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class LocalCommandQueue:
    sac_root: Path

    def get_command(
        self, *, tenant_id: str, idempotency_key: str
    ) -> RunCommandRecord | None:
        path = _command_path(self.sac_root, tenant_id, _validate_idempotency_key(idempotency_key))
        if not path.is_file():
            return None
        return RunCommandRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def record_command(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        command: RunCommandKind,
        run_id: str,
        payload: dict[str, str] | None = None,
    ) -> RunCommandRecord:
        tenant = validate_tenant_id(tenant_id)
        key = _validate_idempotency_key(idempotency_key)
        existing = self.get_command(tenant_id=tenant, idempotency_key=key)
        if existing is not None:
            if existing.command != command or existing.run_id != run_id:
                raise IdempotencyConflictError(
                    f"idempotency key {key!r} already bound to another command"
                )
            return existing
        record = RunCommandRecord(
            tenant_id=tenant,
            idempotency_key=key,
            command=command,
            run_id=run_id,
            payload=dict(payload or {}),
            created_at=_utc_now(),
        )
        _atomic_write_json(
            _command_path(self.sac_root, tenant, key),
            json.loads(record.model_dump_json()),
        )
        return record

    def enqueue_job(
        self,
        *,
        tenant_id: str,
        run_id: str,
        command: RunCommandKind,
        payload: dict[str, str] | None = None,
    ) -> QueueJob:
        tenant = validate_tenant_id(tenant_id)
        job = QueueJob(
            job_id=_job_id(),
            tenant_id=tenant,
            run_id=run_id,
            command=command,
            status="pending",
            payload=dict(payload or {}),
            created_at=_utc_now(),
        )
        root = _queue_root(self.sac_root)
        root.mkdir(parents=True, exist_ok=True)
        pending_path = root / "pending.jsonl"
        with pending_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(json.loads(job.model_dump_json()), sort_keys=True) + "\n")
        return job

    def poll_pending_job(self) -> QueueJob | None:
        root = _queue_root(self.sac_root)
        pending_path = root / "pending.jsonl"
        if not pending_path.is_file():
            return None
        lines = pending_path.read_text(encoding="utf-8").splitlines()
        remaining: list[str] = []
        selected: QueueJob | None = None
        for line in lines:
            if not line.strip():
                continue
            job = QueueJob.model_validate(json.loads(line))
            if selected is None and job.status == "pending":
                selected = job
                continue
            remaining.append(line)
        if selected is not None:
            pending_path.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
            active_path = root / "active.jsonl"
            with active_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(json.loads(selected.model_dump_json()), sort_keys=True) + "\n")
        return selected

    def _rewrite_active(self, jobs: list[QueueJob]) -> None:
        active_path = _queue_root(self.sac_root) / "active.jsonl"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_text(
            "\n".join(
                json.dumps(json.loads(job.model_dump_json()), sort_keys=True) for job in jobs
            )
            + ("\n" if jobs else ""),
            encoding="utf-8",
        )

    def complete_job(self, job_id: str) -> None:
        active_path = _queue_root(self.sac_root) / "active.jsonl"
        if not active_path.is_file():
            return
        jobs = [
            QueueJob.model_validate(json.loads(line))
            for line in active_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        completed = _queue_root(self.sac_root) / "completed.jsonl"
        kept: list[QueueJob] = []
        for job in jobs:
            if job.job_id == job_id:
                finished = job.model_copy(update={"status": "completed"})
                with completed.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(json.loads(finished.model_dump_json()), sort_keys=True) + "\n"
                    )
            else:
                kept.append(job)
        self._rewrite_active(kept)

    def fail_job(self, job_id: str, *, message: str) -> None:
        active_path = _queue_root(self.sac_root) / "active.jsonl"
        if not active_path.is_file():
            return
        jobs = [
            QueueJob.model_validate(json.loads(line))
            for line in active_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        failed_path = _queue_root(self.sac_root) / "failed.jsonl"
        kept: list[QueueJob] = []
        for job in jobs:
            if job.job_id == job_id:
                finished = job.model_copy(
                    update={"status": "failed", "payload": {**job.payload, "error": message[:512]}}
                )
                with failed_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(json.loads(finished.model_dump_json()), sort_keys=True) + "\n"
                    )
            else:
                kept.append(job)
        self._rewrite_active(kept)
