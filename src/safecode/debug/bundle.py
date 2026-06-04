"""Experimental debug bundle creation."""

from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safecode import __version__
from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.doctor import Doctor
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.facade import MemoryFacade
from safecode.project.profile import load_profile
from safecode.task.store import TaskStore
from safecode.utils.time import utc_now_iso

MAX_BUNDLE_BYTES = 5 * 1024 * 1024
DEFAULT_RUNTIME_LIMIT = 100
DEFAULT_AUDIT_LIMIT = 100

_SENSITIVE_WORDS = ("secret", "token", "key", "password", "credential")


@dataclass(frozen=True)
class DebugBundleResult:
    """Result of creating a debug bundle."""

    path: Path
    manifest: dict[str, Any]
    size_bytes: int


def create_debug_bundle(
    project_root: Path,
    *,
    task_id: str | None = None,
    out_path: Path | None = None,
    force: bool = False,
) -> DebugBundleResult:
    """Write a redacted SafeCode metadata bundle as a tar.gz file."""
    root = project_root.resolve()
    target = out_path or _default_out_path(root)
    if target.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing bundle: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    audit_logger = AuditLogger(root)
    ok, integrity_message = audit_logger.verify_integrity()
    if not ok:
        raise ValueError(f"Audit integrity verification failed: {integrity_message}")

    payloads = _bundle_payloads(root, task_id=task_id, audit_integrity=integrity_message)
    _write_tar(target, payloads)
    size = target.stat().st_size
    if size > MAX_BUNDLE_BYTES:
        target.unlink(missing_ok=True)
        raise ValueError("Debug bundle exceeded 5 MiB size limit.")
    manifest = json.loads(payloads["manifest.json"])
    return DebugBundleResult(path=target, manifest=manifest, size_bytes=size)


def _bundle_payloads(project_root: Path, *, task_id: str | None, audit_integrity: str) -> dict[str, str]:
    selected_tasks = _selected_tasks(project_root, task_id)
    payloads: dict[str, Any] = {
        "version.json": {
            "safecode_version": __version__,
            "bundle_schema": "v1",
        },
        "config.json": _redact_for_bundle(SafeCodeConfig.load(project_root).model_dump(mode="json")),
        "doctor.json": _doctor_snapshot(project_root),
        "runtime_logs.json": [
            _redact_for_bundle(event.model_dump(mode="json"))
            for event in RuntimeLogger(project_root).read_recent(limit=DEFAULT_RUNTIME_LIMIT)
        ],
        "audit_events.json": {
            "integrity": audit_integrity,
            "events": [
                _redact_for_bundle(event.model_dump(mode="json"))
                for event in AuditLogger(project_root).iter_events()[-DEFAULT_AUDIT_LIMIT:]
            ],
        },
        "task_sidecars.json": [
            _redact_for_bundle(state.model_dump(mode="json"))
            for state in selected_tasks
        ],
        "project_profile.json": _redact_for_bundle(profile.model_dump(mode="json") if (profile := load_profile(project_root)) else None),
        "memory_metadata.json": _memory_metadata(project_root),
    }
    manifest = {
        "created_at": utc_now_iso(),
        "schema": "safecode-debug-bundle-v1",
        "task_id": task_id,
        "entries": sorted(payloads),
        "excludes_project_source": True,
        "max_size_bytes": MAX_BUNDLE_BYTES,
    }
    payloads["manifest.json"] = manifest
    return {
        name: json.dumps(_redact_for_bundle(value), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        for name, value in payloads.items()
    }


def _write_tar(path: Path, payloads: dict[str, str]) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name in sorted(payloads):
            data = payloads[name].encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))


def _doctor_snapshot(project_root: Path) -> list[dict[str, Any]]:
    checks = Doctor(project_root, fetch_latest_version=lambda: None).run()
    return _redact_for_bundle([
        {"name": check.name, "passed": check.passed, "detail": check.detail}
        for check in checks
    ])


def _selected_tasks(project_root: Path, task_id: str | None):
    store = TaskStore(project_root)
    if task_id:
        state = store.load(task_id)
        return [state] if state is not None else []
    current = store.current_id()
    tasks = list(store.list())
    if current:
        current_state = store.load(current)
        if current_state is not None:
            tasks = [current_state] + [state for state in tasks if state.task_id != current]
    return tasks[:10]


def _memory_metadata(project_root: Path) -> dict[str, Any]:
    facade = MemoryFacade(project_root)
    paths = {
        "project_notes": facade.project_path,
        "recent_failures": facade.recent_failures_path,
        "recent_edits": facade.recent_edits_path,
        "pinned_files": facade.pinned_path,
    }
    result: dict[str, Any] = {}
    for name, path in paths.items():
        result[name] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
    try:
        result["pinned_count"] = len(facade.read_pinned_files())
    except Exception:
        result["pinned_count"] = 0
    return result


def _redact_for_bundle(value: Any) -> Any:
    if isinstance(value, str):
        text = redact_secrets(value)
        for word in _SENSITIVE_WORDS:
            text = text.replace(word, "[REDACTED]").replace(word.upper(), "[REDACTED]").replace(word.title(), "[REDACTED]")
        return text
    if isinstance(value, list):
        return [_redact_for_bundle(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_for_bundle(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            safe_key = key_text
            if any(word in key_text.lower() for word in _SENSITIVE_WORDS):
                safe_key = "redacted_field"
            redacted[safe_key] = _redact_for_bundle(item)
        return redacted
    return value


def _default_out_path(project_root: Path) -> Path:
    return project_root / ".sac" / "debug" / "safecode-debug-bundle.tar.gz"
