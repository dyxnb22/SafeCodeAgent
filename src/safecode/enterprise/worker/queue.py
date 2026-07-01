"""Local command queue and shared queue protocol (v2.1.5-T1).

中文模块说明：本地文件队列与 CommandQueue 协议；Postgres 队列实现同一接口。
- 架构位置：Workflow 平面；API 入队，worker 出队执行。
- 安全不变量：idempotency key 冲突 fail-closed；终端任务不重复执行。
- 学习路径：对照 ``postgres_queue.py`` 与 worker recovery 测试。
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from safecode.context.redactor import redact_secrets
from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.worker.models import QueueJob, RunCommandKind, RunCommandRecord
from safecode.utils.file_lock import atomic_replace_text, keyed_exclusive_lock, lock_path_for

MAX_QUEUE_ATTEMPTS = 3


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


def command_job_id(*, tenant_id: str, idempotency_key: str) -> str:
    tenant = validate_tenant_id(tenant_id)
    key = _validate_idempotency_key(idempotency_key)
    digest = hashlib.sha256(f"{tenant}\0{key}".encode("utf-8")).hexdigest()[:24]
    return f"job-cmd-{digest}"


def validate_command_match(
    existing: RunCommandRecord,
    *,
    command: RunCommandKind,
    run_id: str,
    payload: dict[str, str] | None = None,
) -> None:
    payload_dict = _payload_dict(payload)
    if (
        existing.command != command
        or existing.run_id != run_id
        or existing.payload != payload_dict
    ):
        raise IdempotencyConflictError(
            f"idempotency key {existing.idempotency_key!r} already bound to another command"
        )


def validate_command_binding(
    existing: RunCommandRecord,
    *,
    command: RunCommandKind,
    run_id: str,
    payload: dict[str, str] | None = None,
) -> None:
    """Validate a proposed command against a stored record, allowing start run_id races."""
    payload_dict = _payload_dict(payload)
    if existing.command != command or existing.payload != payload_dict:
        raise IdempotencyConflictError(
            f"idempotency key {existing.idempotency_key!r} already bound to another command"
        )
    if command != "start" and existing.run_id != run_id:
        raise IdempotencyConflictError(
            f"idempotency key {existing.idempotency_key!r} already bound to another command"
        )


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

    def enqueue_command_job(self, record: RunCommandRecord) -> QueueJob: ...

    def poll_pending_job(self) -> QueueJob | None: ...

    def complete_job(self, job_id: str) -> None: ...

    def fail_job(self, job_id: str, *, message: str) -> None: ...

    def retry_job(self, job_id: str, *, message: str) -> bool: ...

    def dlq_job(self, job_id: str, *, message: str, poison: bool = False) -> None: ...


def _commands_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "worker" / "run_commands"


def _payload_dict(payload: dict[str, str] | None) -> dict[str, str]:
    return dict(payload or {})


def _queue_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "worker" / "queue"


def _dlq_path(sac_root: Path) -> Path:
    return _queue_root(sac_root) / "dlq.jsonl"


def _redact_queue_error(message: str) -> str:
    return redact_secrets(message)[:512]


def _command_path(sac_root: Path, tenant_id: str, idempotency_key: str) -> Path:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    return _commands_root(sac_root) / validate_tenant_id(tenant_id) / f"{digest}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_replace_text(path, json.dumps(payload, sort_keys=True, indent=2))


def _queue_lock_path(sac_root: Path) -> Path:
    return lock_path_for(_queue_root(sac_root) / "queue.state")


def _job_from_record(record: RunCommandRecord) -> QueueJob:
    return QueueJob(
        job_id=command_job_id(
            tenant_id=record.tenant_id,
            idempotency_key=record.idempotency_key,
        ),
        tenant_id=record.tenant_id,
        run_id=record.run_id,
        command=record.command,
        status="pending",
        payload=dict(record.payload),
        created_at=_utc_now(),
    )


def ensure_command_enqueued(
    queue: CommandQueue,
    *,
    tenant_id: str,
    idempotency_key: str,
    command: RunCommandKind,
    run_id: str,
    payload: dict[str, str] | None = None,
) -> RunCommandRecord:
    """Record a command and idempotently enqueue its durable command job."""
    tenant = validate_tenant_id(tenant_id)
    key = _validate_idempotency_key(idempotency_key)
    payload_dict = _payload_dict(payload)
    existing = queue.get_command(tenant_id=tenant, idempotency_key=key)
    if existing is not None:
        validate_command_match(
            existing,
            command=command,
            run_id=run_id,
            payload=payload_dict,
        )
        queue.enqueue_command_job(existing)
        return existing
    record = queue.record_command(
        tenant_id=tenant,
        idempotency_key=key,
        command=command,
        run_id=run_id,
        payload=payload_dict,
    )
    queue.enqueue_command_job(record)
    return record


@dataclass(frozen=True)
class LocalCommandQueue:
    sac_root: Path

    def _with_queue_lock(self):
        root = _queue_root(self.sac_root)
        root.mkdir(parents=True, exist_ok=True)
        return keyed_exclusive_lock(str(root.resolve()), _queue_lock_path(self.sac_root))

    def get_command(
        self, *, tenant_id: str, idempotency_key: str
    ) -> RunCommandRecord | None:
        path = _command_path(self.sac_root, tenant_id, _validate_idempotency_key(idempotency_key))
        if not path.is_file():
            return None
        return RunCommandRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def _find_command_job_locked(self, job_id: str) -> QueueJob | None:
        root = _queue_root(self.sac_root)
        for filename in ("pending.jsonl", "active.jsonl", "completed.jsonl", "failed.jsonl"):
            path = root / filename
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                job = QueueJob.model_validate(json.loads(line))
                if job.job_id == job_id:
                    return job
        dlq_path = _dlq_path(self.sac_root)
        if dlq_path.is_file():
            for line in dlq_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                raw = json.loads(line)
                if str(raw.get("job_id")) != job_id:
                    continue
                return QueueJob.model_validate(
                    {
                        "job_id": raw["job_id"],
                        "tenant_id": raw["tenant_id"],
                        "run_id": raw["run_id"],
                        "command": raw["command"],
                        "status": "failed",
                        "payload": dict(raw.get("payload") or {}),
                        "created_at": str(raw.get("created_at", _utc_now())),
                        "attempts": int(raw.get("attempts", 0)),
                    }
                )
        return None

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
        path = _command_path(self.sac_root, tenant, key)
        with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
            existing = self.get_command(tenant_id=tenant, idempotency_key=key)
            if existing is not None:
                validate_command_binding(
                    existing,
                    command=command,
                    run_id=run_id,
                    payload=_payload_dict(payload),
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
            _atomic_write_json(path, json.loads(record.model_dump_json()))
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
        with self._with_queue_lock():
            root = _queue_root(self.sac_root)
            pending_path = root / "pending.jsonl"
            with pending_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(json.loads(job.model_dump_json()), sort_keys=True) + "\n")
        return job

    def enqueue_command_job(self, record: RunCommandRecord) -> QueueJob:
        job = _job_from_record(record)
        with self._with_queue_lock():
            existing = self._find_command_job_locked(job.job_id)
            if existing is not None:
                return existing
            root = _queue_root(self.sac_root)
            pending_path = root / "pending.jsonl"
            with pending_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(json.loads(job.model_dump_json()), sort_keys=True) + "\n")
        return job

    def poll_pending_job(self) -> QueueJob | None:
        with self._with_queue_lock():
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
                atomic_replace_text(
                    pending_path,
                    "\n".join(remaining) + ("\n" if remaining else ""),
                )
                active_path = root / "active.jsonl"
                with active_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(json.loads(selected.model_dump_json()), sort_keys=True) + "\n"
                    )
            return selected

    def _rewrite_active(self, jobs: list[QueueJob]) -> None:
        active_path = _queue_root(self.sac_root) / "active.jsonl"
        atomic_replace_text(
            active_path,
            "\n".join(
                json.dumps(json.loads(job.model_dump_json()), sort_keys=True) for job in jobs
            )
            + ("\n" if jobs else ""),
        )

    def _load_active_jobs(self) -> list[QueueJob]:
        active_path = _queue_root(self.sac_root) / "active.jsonl"
        if not active_path.is_file():
            return []
        return [
            QueueJob.model_validate(json.loads(line))
            for line in active_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def complete_job(self, job_id: str) -> None:
        with self._with_queue_lock():
            active_path = _queue_root(self.sac_root) / "active.jsonl"
            if not active_path.is_file():
                return
            jobs = self._load_active_jobs()
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
        redacted = _redact_queue_error(message)
        with self._with_queue_lock():
            active_path = _queue_root(self.sac_root) / "active.jsonl"
            if not active_path.is_file():
                return
            jobs = self._load_active_jobs()
            failed_path = _queue_root(self.sac_root) / "failed.jsonl"
            kept: list[QueueJob] = []
            for job in jobs:
                if job.job_id == job_id:
                    finished = job.model_copy(
                        update={"status": "failed", "payload": {**job.payload, "error": redacted}}
                    )
                    with failed_path.open("a", encoding="utf-8") as handle:
                        handle.write(
                            json.dumps(json.loads(finished.model_dump_json()), sort_keys=True) + "\n"
                        )
                else:
                    kept.append(job)
            self._rewrite_active(kept)

    def retry_job(self, job_id: str, *, message: str) -> bool:
        redacted = _redact_queue_error(message)
        with self._with_queue_lock():
            jobs = self._load_active_jobs()
            selected: QueueJob | None = None
            kept: list[QueueJob] = []
            for job in jobs:
                if job.job_id == job_id:
                    selected = job
                else:
                    kept.append(job)
            if selected is None:
                return False
            next_attempts = selected.attempts + 1
            if next_attempts >= MAX_QUEUE_ATTEMPTS:
                return False
            self._rewrite_active(kept)
            retried = selected.model_copy(
                update={
                    "status": "pending",
                    "attempts": next_attempts,
                    "payload": {**selected.payload, "last_error": redacted},
                }
            )
            pending_path = _queue_root(self.sac_root) / "pending.jsonl"
            with pending_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(json.loads(retried.model_dump_json()), sort_keys=True) + "\n")
            return True

    def dlq_job(self, job_id: str, *, message: str, poison: bool = False) -> None:
        redacted = _redact_queue_error(message)
        with self._with_queue_lock():
            jobs = self._load_active_jobs()
            kept: list[QueueJob] = []
            selected: QueueJob | None = None
            for job in jobs:
                if job.job_id == job_id:
                    selected = job
                else:
                    kept.append(job)
            if selected is None:
                return
            self._rewrite_active(kept)
            dlq_record = {
                **json.loads(selected.model_dump_json()),
                "status": "failed",
                "poison": poison,
                "error": redacted,
                "dlq_at": _utc_now(),
            }
            dlq_path = _dlq_path(self.sac_root)
            dlq_path.parent.mkdir(parents=True, exist_ok=True)
            with dlq_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dlq_record, sort_keys=True) + "\n")
