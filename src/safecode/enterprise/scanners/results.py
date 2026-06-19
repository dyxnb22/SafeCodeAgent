"""Structured CI scanner callback results (v2.2.4-T2)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.persistence.webhook_store import payload_digest
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.orchestrator import utc_now_iso
from safecode.enterprise.workflow.state import ValidationResult

CI_CALLBACK_SCHEMA_VERSION = "1.0"
MAX_CI_CALLBACK_BODY_BYTES = 64 * 1024
SUPPORTED_CI_OUTCOMES = frozenset({"passed", "failed"})


class CiCallbackSchemaError(Exception):
    """Raised when callback payload fails schema validation."""


class CiCallbackSignatureError(Exception):
    """Raised when callback signature verification fails."""


class CiCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CI_CALLBACK_SCHEMA_VERSION
    delivery_id: str = Field(min_length=8, max_length=128)
    run_id: str = Field(min_length=8, max_length=128)
    outcome: Literal["passed", "failed"]
    commit_sha: str | None = Field(default=None, min_length=40, max_length=40)
    scanner: str | None = Field(default=None, max_length=64)
    tool_version: str | None = Field(default=None, max_length=64)


class CiCallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str
    run_id: str
    status: Literal["accepted"] = "accepted"
    replay: Literal["true", "false"] = "false"


class CiScannerResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    delivery_id: str
    run_id: str
    tenant_id: str
    outcome: Literal["passed", "failed"]
    commit_sha: str | None = None
    scanner: str | None = None
    tool_version: str | None = None
    payload_digest: str
    created_at: str


def sign_ci_callback_body(body: bytes, *, secret: str) -> str:
    """Test helper to produce a valid X-CI-Signature-256 header."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_ci_callback_signature(
    *,
    body: bytes,
    secret: str,
    signature_header: str | None,
) -> None:
    """Validate CI callback HMAC signature against the raw request body."""
    if signature_header is None or not signature_header.startswith("sha256="):
        raise CiCallbackSignatureError("missing or invalid ci callback signature")
    if len(body) > MAX_CI_CALLBACK_BODY_BYTES:
        raise CiCallbackSignatureError("ci callback body exceeds size limit")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise CiCallbackSignatureError("ci callback signature mismatch")


def parse_ci_callback_request(body: bytes) -> CiCallbackRequest:
    """Parse and validate a CI callback payload; reject schema mismatches."""
    if len(body) > MAX_CI_CALLBACK_BODY_BYTES:
        raise CiCallbackSchemaError("ci callback body exceeds size limit")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CiCallbackSchemaError("invalid ci callback json payload") from exc
    if not isinstance(payload, dict):
        raise CiCallbackSchemaError("invalid ci callback json payload")
    try:
        request = CiCallbackRequest.model_validate(payload)
    except ValidationError as exc:
        raise CiCallbackSchemaError(str(exc)) from exc
    if request.schema_version != CI_CALLBACK_SCHEMA_VERSION:
        raise CiCallbackSchemaError(
            f"unsupported ci callback schema version: {request.schema_version!r}"
        )
    if request.outcome not in SUPPORTED_CI_OUTCOMES:
        raise CiCallbackSchemaError(f"unsupported outcome: {request.outcome!r}")
    return request


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _result_path(sac_root: Path, run_id: str, delivery_id: str) -> Path:
    digest = hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()[:32]
    return sac_root / "enterprise" / "ci" / "results" / run_id / f"{digest}.json"


def _atomic_write_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_ci_result_record(sac_root: Path, *, run_id: str, delivery_id: str) -> CiScannerResultRecord | None:
    path = _result_path(sac_root, run_id, delivery_id)
    if not path.is_file():
        return None
    return CiScannerResultRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_ci_result_record(sac_root: Path, record: CiScannerResultRecord) -> CiScannerResultRecord:
    _atomic_write_json(
        _result_path(sac_root, record.run_id, record.delivery_id),
        record.model_dump(),
    )
    return record


def apply_ci_callback_to_run(
    backend: object,
    *,
    tenant_id: str,
    request: CiCallbackRequest,
    payload_digest_value: str,
) -> CiScannerResultRecord:
    """Persist callback result and update the matching run validation state."""
    tenant = validate_tenant_id(tenant_id)
    runs = getattr(backend, "runs", None)
    trace = getattr(backend, "trace", None)
    sac_root = getattr(backend, "sac_root", None)
    if runs is None or sac_root is None:
        raise TypeError("backend does not expose runs or sac_root")

    checkpoint = runs.load_checkpoint(tenant_id=tenant, run_id=request.run_id)
    state = checkpoint.state
    if state.tenant_id != tenant:
        raise ValueError("tenant scope mismatch for run")

    if request.commit_sha is not None:
        repo_commit = (state.repo.commit_sha if state.repo else "").lower()
        if repo_commit and repo_commit not in {"0000000", "0" * 40} and repo_commit != request.commit_sha.lower():
            raise ValueError("commit sha mismatch for run")

    existing = load_ci_result_record(sac_root, run_id=request.run_id, delivery_id=request.delivery_id)
    if existing is not None:
        if existing.payload_digest != payload_digest_value or existing.tenant_id != tenant:
            raise ValueError("delivery id already bound to a different payload")
        return existing

    passed = request.outcome == "passed"
    validation = ValidationResult(
        passed=passed,
        summary=f"ci callback outcome={request.outcome}",
        details={
            "source": "ci_callback",
            "delivery_id": request.delivery_id,
            "outcome": request.outcome,
            "scanner": request.scanner or "",
            "tool_version": request.tool_version or "",
            "commit_sha": request.commit_sha or "",
        },
    )
    updated_state = state.model_copy(
        update={
            "validation": validation,
            "validation_failed": not passed,
            "updated_at": utc_now_iso(),
        }
    )
    runs.save_checkpoint(
        tenant_id=tenant,
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=request.run_id,
            completed_nodes=list(checkpoint.completed_nodes),
            next_node=checkpoint.next_node,
            state=updated_state,
        ),
    )

    record = CiScannerResultRecord(
        schema_version=CI_CALLBACK_SCHEMA_VERSION,
        delivery_id=request.delivery_id,
        run_id=request.run_id,
        tenant_id=tenant,
        outcome=request.outcome,
        commit_sha=request.commit_sha,
        scanner=request.scanner,
        tool_version=request.tool_version,
        payload_digest=payload_digest_value,
        created_at=_utc_now(),
    )
    save_ci_result_record(sac_root, record)

    if trace is not None:
        trace.emit_event(
            tenant_id=tenant,
            run_id=request.run_id,
            event_type=TraceEventType.validation_result,
            node_id="ci_callback",
            seq=1,
            payload={
                "source": "ci_callback",
                "delivery_id": request.delivery_id,
                "outcome": request.outcome,
            },
            actor_id="ci:callback",
        )

    return record


def digest_ci_callback_body(body: bytes) -> str:
    return payload_digest(body)
