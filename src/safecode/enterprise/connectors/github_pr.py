"""GitHub pull request connector (fixture-first)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from safecode.context.redactor import redact_secrets
from safecode.enterprise.connectors.models import DiffHunk, PullRequestEvidence, PullRequestFile

MAX_BODY_CHARS = 32_768
MAX_FILES = 200
MAX_HUNKS = 500
MAX_HUNK_PATCH_CHARS = 8_192
MAX_TITLE_CHARS = 512

_GH_TOKEN_RE = re.compile(r"gh[ps]_[A-Za-z0-9]{20,}")
_AUTH_HEADER_RE = re.compile(r"Authorization\s*:\s*[^\n]+", re.IGNORECASE)


class ConnectorError(Exception):
    """Base connector error."""


class ConnectorBoundsError(ConnectorError):
    """Raised when fixture input exceeds configured bounds."""


class PullRequestConnectorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixture", "live"] = "fixture"
    fixture_path: str | None = None
    owner: str | None = None
    repo: str | None = None
    pr_number: int | None = None
    project_root: str = "."


def redact_connector_text(text: str) -> str:
    cleaned = _AUTH_HEADER_RE.sub("[REDACTED_AUTH]", text)
    cleaned = _GH_TOKEN_RE.sub("[REDACTED_TOKEN]", cleaned)
    return redact_secrets(cleaned)


def _stable_hunk_id(file_path: str, start_line: int, end_line: int, patch: str) -> str:
    payload = f"{file_path}:{start_line}:{end_line}:{patch}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"hunk-{digest}"


def _stable_evidence_id(title: str, base_ref: str, head_ref: str) -> str:
    payload = f"{title}:{base_ref}:{head_ref}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"pre-{digest}"


def _resolve_fixture_path(spec: PullRequestConnectorSpec) -> Path:
    if not spec.fixture_path:
        raise ConnectorError("fixture_path is required for fixture mode")
    root = Path(spec.project_root).resolve()
    path = (root / spec.fixture_path).resolve()
    if root not in path.parents and path != root:
        raise ConnectorError("fixture path escapes project root")
    if not path.is_file():
        raise ConnectorError(f"fixture not found: {spec.fixture_path}")
    return path


def parse_fixture_payload(payload: dict) -> PullRequestEvidence:
    title = redact_connector_text(str(payload.get("title", "")))[:MAX_TITLE_CHARS]
    body = redact_connector_text(str(payload.get("body", "")))[:MAX_BODY_CHARS]
    files_raw = list(payload.get("files") or [])
    hunks_raw = list(payload.get("hunks") or [])
    if len(files_raw) > MAX_FILES:
        raise ConnectorBoundsError(f"too many files: {len(files_raw)} > {MAX_FILES}")
    if len(hunks_raw) > MAX_HUNKS:
        raise ConnectorBoundsError(f"too many hunks: {len(hunks_raw)} > {MAX_HUNKS}")

    files = [
        PullRequestFile(path=str(item.get("path", "")), status=item.get("status", "modified"))
        for item in files_raw
    ]
    hunks: list[DiffHunk] = []
    for item in hunks_raw:
        patch = redact_connector_text(str(item.get("patch", "")))[:MAX_HUNK_PATCH_CHARS]
        file_path = str(item.get("file_path", ""))
        start_line = int(item.get("start_line", 0))
        end_line = int(item.get("end_line", start_line))
        hunks.append(
            DiffHunk(
                hunk_id=_stable_hunk_id(file_path, start_line, end_line, patch),
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                patch=patch,
            )
        )

    base_ref = str(payload.get("base_ref", "main"))
    head_ref = str(payload.get("head_ref", "feature"))
    return PullRequestEvidence(
        evidence_id=_stable_evidence_id(title, base_ref, head_ref),
        title=title,
        body=body,
        author=str(payload.get("author", "unknown")),
        base_ref=base_ref,
        head_ref=head_ref,
        labels=[str(label) for label in payload.get("labels") or []],
        reviewers=[str(name) for name in payload.get("reviewers") or []],
        files=files,
        hunks=hunks,
    )


def fetch_pr(spec: PullRequestConnectorSpec) -> PullRequestEvidence:
    if spec.mode == "live":
        raise ConnectorError("live PR fetch is not enabled in v1.3; use fixture mode")
    path = _resolve_fixture_path(spec)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_fixture_payload(payload)
