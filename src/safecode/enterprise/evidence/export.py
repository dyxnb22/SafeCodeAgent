"""Compliance evidence export bundle builder."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from safecode.audit.models import AuditEvent
from safecode.enterprise.approvals.store import list_requests
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.tenant import filter_audit_events_by_tenant
from safecode.enterprise.trace.emitter import trace_file_path
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.trace.timeline import build_timeline, serialize_timeline
from safecode.enterprise.trace.redaction import apply_profile_to_text
from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.exceptions import InvalidRunIdError
from safecode.enterprise.workflow.ids import validate_run_id

EVIDENCE_SCHEMA_VERSION = "1.0"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_audit_event(event: AuditEvent) -> str:
    data = event.model_dump()
    data["event_hash"] = None
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_audit_segment(events: list[AuditEvent]) -> tuple[bool, str]:
    if not events:
        return True, "no audit events in bundle"
    for index, event in enumerate(events, start=1):
        if event.event_hash != _hash_audit_event(event):
            return False, f"audit hash mismatch at event {index}"
    return True, "audit event hashes intact"


def _strict_redact(value: object, field_name: str = "value") -> object:
    if isinstance(value, str):
        return apply_profile_to_text(field_name, value, profile="strict")[0]
    if isinstance(value, list):
        return [_strict_redact(item, field_name) for item in value]
    if isinstance(value, dict):
        return {str(key): _strict_redact(item, str(key)) for key, item in value.items()}
    return value


def _json_bytes(value: object) -> bytes:
    return json.dumps(_strict_redact(value), sort_keys=True, indent=2).encode("utf-8")


def export_run_evidence(sac_root: Path, run_id: str, *, tenant_id: str) -> Path:
    """Build a redacted compliance zip for one workflow run."""
    validate_run_id(run_id)
    project_root = project_root_for_sac(sac_root)
    checkpoint = load_checkpoint(sac_root, run_id)
    state = checkpoint.state
    if state.tenant_id != tenant_id:
        raise PermissionError("evidence export tenant does not match workflow tenant")
    timeline = build_timeline(sac_root, run_id)
    run_dir = trace_file_path(sac_root, run_id).parent
    if not run_dir.is_dir():
        raise InvalidRunIdError(f"run directory missing: {run_id}")

    bundle_id = f"bundle-{run_id}"[:64]
    zip_path = sac_root / "enterprise" / "evidence" / f"{bundle_id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    files: dict[str, bytes] = {}
    trace_path = run_dir / "trace.jsonl"
    if trace_path.is_file():
        trace_lines = [
            json.dumps(_strict_redact(json.loads(line)), ensure_ascii=False, sort_keys=True)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        files["trace.jsonl"] = (("\n".join(trace_lines) + "\n") if trace_lines else "").encode(
            "utf-8"
        )

    files["state.json"] = _json_bytes(state.model_dump(mode="json"))
    files["timeline.json"] = _json_bytes(json.loads(serialize_timeline(timeline)))
    files["citations.json"] = _json_bytes(
        [item.model_dump(mode="json") for item in state.citations]
    )
    files["approvals.json"] = _json_bytes(
        [item.model_dump(mode="json") for item in list_requests(sac_root, run_id)]
    )
    if state.validation is not None:
        files["validation.json"] = _json_bytes(state.validation.model_dump(mode="json"))
    if state.report is not None:
        files["report.md"] = apply_profile_to_text(
            "report", state.report.markdown, profile="strict"
        )[0].encode("utf-8")

    audit = EnterpriseAuditChain(project_root)
    source_audit_ok, source_audit_message = audit.verify_integrity()
    if not source_audit_ok:
        raise ValueError(f"source audit chain verification failed: {source_audit_message}")
    audit_events = filter_audit_events_by_tenant(
        audit.iter_events(), state.tenant_id, run_id=run_id
    )
    audit_lines = "\n".join(
        json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True) for event in audit_events
    )
    if audit_lines:
        files["audit_chain.jsonl"] = (audit_lines + "\n").encode("utf-8")

    manifest = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "run_id": run_id,
        "tenant_id": state.tenant_id,
        "task_type": state.task_type.value,
        "source_audit_chain_verified": True,
        "files": [
            {"name": name, "sha256": _sha256_bytes(content)} for name, content in sorted(files.items())
        ],
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    return zip_path


def verify_export_bundle(zip_path: Path) -> tuple[bool, str]:
    """Verify manifest hashes and audit segment integrity inside an export zip."""
    if not zip_path.is_file():
        return False, "bundle missing"
    with zipfile.ZipFile(zip_path, "r") as archive:
        manifest_raw = archive.read("manifest.json")
        manifest = json.loads(manifest_raw.decode("utf-8"))
        for entry in manifest.get("files", []):
            name = entry["name"]
            if name == "manifest.json":
                continue
            content = archive.read(name)
            digest = _sha256_bytes(content)
            if digest != entry.get("sha256"):
                return False, f"hash mismatch for {name}"
        manifest_digest = _sha256_bytes(manifest_raw)
        listed = next((item for item in manifest.get("files", []) if item["name"] == "manifest.json"), None)
        if listed and listed.get("sha256") != manifest_digest:
            return False, "manifest self-hash mismatch"
        if "audit_chain.jsonl" not in archive.namelist():
            return True, "bundle verified (no audit segment)"
        events = [
            AuditEvent(**json.loads(line))
            for line in archive.read("audit_chain.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]
        return _verify_audit_segment(events)
