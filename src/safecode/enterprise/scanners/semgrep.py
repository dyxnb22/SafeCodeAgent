"""Semgrep finding normalizer."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from safecode.context.redactor import redact_secrets
from safecode.enterprise.scanners.models import Location, SecurityFinding
from safecode.enterprise.workflow.types import RiskTier

SUPPORTED_SCHEMA_VERSION = 1


class ScannerError(Exception):
    """Scanner normalization error."""


class UnsupportedScannerVersionError(ScannerError):
    """Raised when scanner output schema is unsupported."""


def _finding_id(rule_id: str, path: str, start_line: int) -> str:
    digest = hashlib.sha256(f"{rule_id}:{path}:{start_line}".encode("utf-8")).hexdigest()[:16]
    return f"finding-{digest}"


def _map_severity(raw: str) -> RiskTier:
    value = raw.upper()
    if value in {"ERROR", "HIGH", "CRITICAL"}:
        return RiskTier.high
    if value in {"WARNING", "MEDIUM"}:
        return RiskTier.medium
    return RiskTier.low


def normalize_semgrep(payload: dict[str, Any], *, schema_version: int = SUPPORTED_SCHEMA_VERSION) -> list[SecurityFinding]:
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise UnsupportedScannerVersionError(f"unsupported semgrep schema version: {schema_version}")
    if "results" not in payload:
        raise UnsupportedScannerVersionError("missing semgrep results key")
    findings: list[SecurityFinding] = []
    for item in payload.get("results") or []:
        rule_id = str(item.get("check_id") or item.get("rule_id") or "unknown")
        path = str(item.get("path") or "unknown")
        start = int((item.get("start") or {}).get("line") or 0)
        end = int((item.get("end") or {}).get("line") or start)
        extra = item.get("extra") or {}
        title = redact_secrets(str(extra.get("message") or rule_id))[:512]
        description = redact_secrets(str(extra.get("message") or ""))[:4096]
        cwe_list = (extra.get("metadata") or {}).get("cwe") or []
        cwe = str(cwe_list[0]) if cwe_list else None
        snippet_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()
        findings.append(
            SecurityFinding(
                finding_id=_finding_id(rule_id, path, start),
                source="semgrep",
                rule_id=rule_id,
                severity=_map_severity(str(extra.get("severity") or "INFO")),
                title=title,
                description=description,
                cwe=cwe,
                location=Location(path=path, start_line=start, end_line=end, snippet_hash=f"sha256:{snippet_hash[:16]}"),
            )
        )
    return findings


def normalize_semgrep_json(raw: str) -> list[SecurityFinding]:
    return normalize_semgrep(json.loads(raw))
