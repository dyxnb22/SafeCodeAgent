"""pip-audit finding normalizer."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from safecode.context.redactor import redact_secrets
from safecode.enterprise.scanners.models import Location, SecurityFinding
from safecode.enterprise.workflow.types import RiskTier


class PipAuditError(Exception):
    """pip-audit normalization error."""


def _finding_id(cve: str, package: str, version: str) -> str:
    digest = hashlib.sha256(f"{cve}:{package}:{version}".encode("utf-8")).hexdigest()[:16]
    return f"finding-{digest}"


def _map_severity(raw: str | None) -> RiskTier:
    value = (raw or "unknown").lower()
    if value in {"critical", "high"}:
        return RiskTier.high
    if value in {"medium", "moderate"}:
        return RiskTier.medium
    if value == "low":
        return RiskTier.low
    return RiskTier.medium


def normalize_pip_audit(payload: dict[str, Any] | list[Any]) -> list[SecurityFinding]:
    rows = payload.get("dependencies") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise PipAuditError("invalid pip-audit payload")
    findings: list[SecurityFinding] = []
    for dep in rows:
        package = str(dep.get("name") or "unknown")
        version = str(dep.get("version") or "unknown")
        for vuln in dep.get("vulns") or []:
            cve = str(vuln.get("id") or "unknown")
            advisory = str(vuln.get("fix_versions") or vuln.get("description") or "")
            title = redact_secrets(f"{package} {version}: {cve}")[:512]
            description = redact_secrets(advisory)[:4096]
            findings.append(
                SecurityFinding(
                    finding_id=_finding_id(cve, package, version),
                    source="pip_audit",
                    rule_id=cve,
                    severity=_map_severity(vuln.get("severity")),
                    title=title,
                    description=description,
                    cve=cve,
                    location=Location(
                        path=f"pkg:{package}",
                        start_line=0,
                        end_line=0,
                        snippet_hash=f"sha256:{hashlib.sha256(description.encode()).hexdigest()[:16]}",
                    ),
                )
            )
    return findings


def normalize_pip_audit_json(raw: str) -> list[SecurityFinding]:
    return normalize_pip_audit(json.loads(raw))
