"""Issue tracker connector (fixture-only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from safecode.context.redactor import redact_secrets
from safecode.enterprise.connectors.models import IssueEvidence

MAX_BODY_CHARS = 32_768
MAX_TITLE_CHARS = 512
_SEVERITY_MAP = {
    "unknown": "unknown",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
    "blocker": "critical",
    "major": "high",
    "minor": "low",
}


class IssueConnectorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixture", "live"] = "fixture"
    source_kind: Literal["markdown", "jira_json"] = "markdown"
    source_path: str = ""
    project_root: str = "."
    issue_key: str | None = None
    api_base_url: str = "https://example.atlassian.net"


class IssueConnectorError(Exception):
    """Issue connector error."""


def _resolve_source(spec: IssueConnectorSpec) -> Path:
    root = Path(spec.project_root).resolve()
    path = (root / spec.source_path).resolve()
    if root not in path.parents and path != root:
        raise IssueConnectorError("issue source path escapes project root")
    if not path.is_file():
        raise IssueConnectorError(f"issue source not found: {spec.source_path}")
    return path


def _normalize_severity(raw: str | None) -> Literal["unknown", "low", "medium", "high", "critical"]:
    if not raw:
        return "unknown"
    return _SEVERITY_MAP.get(str(raw).strip().lower(), "unknown")


def _from_markdown(text: str, issue_id: str) -> IssueEvidence:
    lines = text.splitlines()
    title = redact_secrets(lines[0].lstrip("# ").strip() if lines else "Untitled")[:MAX_TITLE_CHARS]
    body = redact_secrets("\n".join(lines[1:]).strip())[:MAX_BODY_CHARS]
    labels: list[str] = []
    severity = "unknown"
    for line in lines:
        if line.lower().startswith("severity:"):
            severity = _normalize_severity(line.split(":", 1)[1])
        if line.lower().startswith("labels:"):
            labels = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
    return IssueEvidence(
        evidence_id=f"issue-{issue_id}",
        issue_id=issue_id,
        title=title,
        body=body,
        labels=labels,
        severity=severity,
        reporter="unknown",
        linked_prs=[],
    )


def _from_jira_json(payload: dict) -> IssueEvidence:
    fields = payload.get("fields") or payload
    issue_id = str(payload.get("key") or payload.get("id") or "unknown")
    title = redact_secrets(str(fields.get("summary") or fields.get("title") or "Untitled"))[:MAX_TITLE_CHARS]
    body = redact_secrets(str(fields.get("description") or fields.get("body") or ""))[:MAX_BODY_CHARS]
    labels: list[str] = []
    for item in fields.get("labels", []):
        if isinstance(item, dict):
            labels.append(str(item.get("name", "")))
        elif item:
            labels.append(str(item))
    severity = _normalize_severity(
        (fields.get("priority") or {}).get("name") if isinstance(fields.get("priority"), dict) else fields.get("severity")
    )
    reporter = ""
    if isinstance(fields.get("reporter"), dict):
        reporter = str(fields["reporter"].get("emailAddress") or fields["reporter"].get("displayName") or "")
    linked = [str(item) for item in fields.get("linked_prs") or []]
    return IssueEvidence(
        evidence_id=f"issue-{issue_id}",
        issue_id=issue_id,
        title=title,
        body=body,
        labels=labels,
        severity=severity,
        reporter=redact_secrets(reporter),
        linked_prs=linked,
    )


def fetch_issue(
    spec: IssueConnectorSpec,
    *,
    email: str | None = None,
    api_token: SecretStr | None = None,
    transport: httpx.BaseTransport | None = None,
) -> IssueEvidence:
    if spec.mode == "live":
        from safecode.enterprise.connectors.jira_live import IssueLiveConnectorSpec, fetch_issue_live

        issue_key = (spec.issue_key or "").strip()
        if not issue_key:
            raise IssueConnectorError("issue_key is required for live issue fetch")
        if email is None or api_token is None:
            raise IssueConnectorError("email and api_token are required for live issue fetch")
        return fetch_issue_live(
            IssueLiveConnectorSpec(issue_key=issue_key, api_base_url=spec.api_base_url),
            email=email,
            api_token=api_token,
            transport=transport,
        )
    if not spec.source_path:
        raise IssueConnectorError("source_path is required for fixture issue fetch")
    path = _resolve_source(spec)
    if spec.source_kind == "markdown":
        issue_id = re.sub(r"[^A-Za-z0-9_-]+", "-", path.stem)[:64] or "unknown"
        return _from_markdown(path.read_text(encoding="utf-8"), issue_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _from_jira_json(payload)
