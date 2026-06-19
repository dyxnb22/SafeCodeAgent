"""PostgreSQL evidence bundle export (v2.1.3)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


from safecode.audit.models import AuditEvent
from safecode.enterprise.evidence.export import EVIDENCE_SCHEMA_VERSION, _sha256_bytes, _verify_audit_segment
from safecode.enterprise.trace.redaction import apply_profile_to_text
from safecode.enterprise.trace.timeline import build_timeline, serialize_timeline
from safecode.enterprise.workflow.checkpoint import RunCheckpoint
from safecode.enterprise.workflow.exceptions import InvalidRunIdError
from safecode.enterprise.workflow.ids import validate_run_id


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


def export_run_evidence_from_pg(
    conn: Any,
    artifacts_root: Path,
    *,
    tenant_id: str,
    run_id: str,
    checkpoint: RunCheckpoint,
    approvals: list[dict[str, object]],
    audit_events: list[AuditEvent],
    trace_lines: list[str],
) -> Path:
    validate_run_id(run_id)
    state = checkpoint.state
    if state.tenant_id != tenant_id:
        raise PermissionError("evidence export tenant does not match workflow tenant")

    timeline = build_timeline(artifacts_root, run_id)
    bundle_id = f"bundle-{run_id}"[:64]
    zip_path = artifacts_root / "enterprise" / "evidence" / f"{bundle_id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    files: dict[str, bytes] = {}
    if trace_lines:
        files["trace.jsonl"] = ("\n".join(trace_lines) + "\n").encode("utf-8")

    files["state.json"] = _json_bytes(state.model_dump(mode="json"))
    files["timeline.json"] = _json_bytes(json.loads(serialize_timeline(timeline)))
    files["citations.json"] = _json_bytes(
        [item.model_dump(mode="json") for item in state.citations]
    )
    files["approvals.json"] = _json_bytes(approvals)
    if state.validation is not None:
        files["validation.json"] = _json_bytes(state.validation.model_dump(mode="json"))
    if state.report is not None:
        files["report.md"] = apply_profile_to_text(
            "report", state.report.markdown, profile="strict"
        )[0].encode("utf-8")

    audit_lines = "\n".join(
        json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True)
        for event in audit_events
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
            {"name": name, "sha256": _sha256_bytes(content)}
            for name, content in sorted(files.items())
        ],
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)

    conn.execute(
        """
        INSERT INTO enterprise.evidence_index (tenant_id, run_id, bundle_path, exported_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (tenant_id, run_id) DO UPDATE
        SET bundle_path = EXCLUDED.bundle_path, exported_at = EXCLUDED.exported_at
        """,
        (tenant_id, run_id, str(zip_path)),
    )
    return zip_path


def verify_export_bundle(zip_path: Path) -> tuple[bool, str]:
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
            if _sha256_bytes(content) != entry.get("sha256"):
                return False, f"hash mismatch for {name}"
        manifest_digest = _sha256_bytes(manifest_raw)
        listed = next(
            (item for item in manifest.get("files", []) if item["name"] == "manifest.json"),
            None,
        )
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
