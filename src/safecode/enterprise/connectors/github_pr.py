"""GitHub pull request connector (fixture-first, live adapter v2.2.2-T1)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from safecode.context.redactor import redact_secrets
from safecode.enterprise.connectors.models import DiffHunk, PullRequestEvidence, PullRequestFile

MAX_BODY_CHARS = 32_768
MAX_FILES = 200
MAX_HUNKS = 500
MAX_HUNK_PATCH_CHARS = 8_192
MAX_TITLE_CHARS = 512
MAX_RESPONSE_BYTES = 1_048_576

_GH_TOKEN_RE = re.compile(r"gh[ps]_[A-Za-z0-9]{20,}")
_AUTH_HEADER_RE = re.compile(r"Authorization\s*:\s*[^\n]+", re.IGNORECASE)
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


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
    installation_id: str | None = None
    api_base_url: str = "https://api.github.com"


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


def _parse_patch_hunks(file_path: str, patch: str) -> list[dict[str, object]]:
    if not patch.strip():
        return []
    headers = list(_HUNK_HEADER_RE.finditer(patch))
    if not headers:
        raise ConnectorError("malformed diff patch: missing hunk header")
    hunks: list[dict[str, object]] = []
    for index, match in enumerate(headers):
        start_line = int(match.group(1))
        count = int(match.group(2)) if match.group(2) else 1
        end_line = start_line + max(count, 1) - 1
        chunk_start = match.start()
        chunk_end = headers[index + 1].start() if index + 1 < len(headers) else len(patch)
        hunk_patch = patch[chunk_start:chunk_end].rstrip()
        hunks.append(
            {
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "patch": hunk_patch,
            }
        )
    return hunks


def _github_status_to_status(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in {"added", "modified", "removed", "renamed"}:
        return normalized
    return "modified"


def _github_pull_to_fixture_payload(pull: dict, files_payload: list[dict]) -> dict:
    labels = [str(item.get("name", "")) for item in pull.get("labels") or [] if item.get("name")]
    reviewers = [
        str(item.get("login", ""))
        for item in pull.get("requested_reviewers") or []
        if item.get("login")
    ]
    files = [
        {
            "path": str(item.get("filename", "")),
            "status": _github_status_to_status(str(item.get("status", "modified"))),
        }
        for item in files_payload
    ]
    hunks: list[dict[str, object]] = []
    for item in files_payload:
        filename = str(item.get("filename", ""))
        patch = str(item.get("patch") or "")
        hunks.extend(_parse_patch_hunks(filename, patch))
    user = pull.get("user") or {}
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    return {
        "title": str(pull.get("title", "")),
        "body": str(pull.get("body") or ""),
        "author": str(user.get("login", "unknown")),
        "base_ref": str(base.get("ref", "main")),
        "head_ref": str(head.get("ref", "feature")),
        "labels": labels,
        "reviewers": reviewers,
        "files": files,
        "hunks": hunks,
    }


def _parse_next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        match = _LINK_NEXT_RE.search(part.strip())
        if match:
            return match.group(1)
    return None


def _validate_live_response(response: httpx.Response) -> None:
    if response.status_code in {301, 302, 303, 307, 308}:
        raise ConnectorError("redirect responses are not allowed for live PR fetch")
    if response.status_code == 429:
        raise ConnectorError("GitHub rate limit exhausted")
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise ConnectorError("GitHub response exceeds size limit")
        except ValueError:
            raise ConnectorError("malformed GitHub response headers") from None
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ConnectorError("GitHub response exceeds size limit")


def _raise_for_live_status(
    response: httpx.Response,
    *,
    installation_id: str | None,
    context: str,
) -> None:
    _validate_live_response(response)
    if response.status_code >= 400:
        detail = redact_connector_text(redact_secrets(response.text[:512]))
        if response.status_code in {403, 404}:
            if installation_id:
                raise ConnectorError(
                    f"{context}: repository not found or installation mismatch"
                )
            raise ConnectorError(f"{context}: repository access denied")
        raise ConnectorError(f"{context} failed ({response.status_code}): {detail}")


def _request_path(client: httpx.Client, path: str, *, headers: dict[str, str]) -> httpx.Response:
    return client.get(path, headers=headers)


def _request_url(client: httpx.Client, url: str, *, headers: dict[str, str]) -> httpx.Response:
    parsed = urlparse(url)
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return client.get(path, headers=headers)


@dataclass
class GitHubPullRequestClient:
    """Fetch pull request evidence using recorded or live HTTP transport."""

    _owner: str
    _repo: str
    _access_token: SecretStr
    _api_base_url: str = "https://api.github.com"
    _installation_id: str | None = None
    _transport: httpx.BaseTransport | None = field(default=None, repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_spec(
        cls,
        spec: PullRequestConnectorSpec,
        *,
        access_token: SecretStr,
        transport: httpx.BaseTransport | None = None,
    ) -> GitHubPullRequestClient:
        owner = (spec.owner or "").strip()
        repo = (spec.repo or "").strip()
        if not owner or not repo:
            raise ConnectorError("owner and repo are required for live PR fetch")
        return cls(
            _owner=owner,
            _repo=repo,
            _access_token=access_token,
            _api_base_url=spec.api_base_url.rstrip("/"),
            _installation_id=(spec.installation_id or "").strip() or None,
            _transport=transport,
        )

    def __repr__(self) -> str:
        return (
            "GitHubPullRequestClient("
            f"owner={self._owner!r}, "
            f"repo={self._repo!r}, "
            "access_token=SecretStr('**********'), "
            f"installation_id={self._installation_id!r})"
        )

    def _http(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                transport=self._transport,
                base_url=self._api_base_url,
                timeout=30.0,
                follow_redirects=False,
            )
        return self._http_client

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
        }

    def _fetch_files(self, client: httpx.Client, pr_number: int) -> list[dict]:
        headers = self._auth_headers()
        path = f"/repos/{self._owner}/{self._repo}/pulls/{pr_number}/files"
        collected: list[dict] = []
        next_path: str | None = path
        while next_path is not None:
            if next_path.startswith("http"):
                response = _request_url(client, next_path, headers=headers)
            else:
                response = _request_path(client, next_path, headers=headers)
            _raise_for_live_status(
                response,
                installation_id=self._installation_id,
                context="pull request files fetch",
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ConnectorError("malformed GitHub files response") from exc
            if not isinstance(payload, list):
                raise ConnectorError("malformed GitHub files response")
            collected.extend(payload)
            if len(collected) > MAX_FILES:
                raise ConnectorBoundsError(f"too many files: {len(collected)} > {MAX_FILES}")
            next_link = _parse_next_link(response.headers.get("Link", ""))
            next_path = None
            if next_link:
                if next_link.startswith(self._api_base_url):
                    next_path = next_link[len(self._api_base_url) :]
                else:
                    next_path = next_link
        return collected

    def fetch(self, pr_number: int) -> PullRequestEvidence:
        if pr_number <= 0:
            raise ConnectorError("pr_number must be positive")
        client = self._http()
        headers = self._auth_headers()
        pull_path = f"/repos/{self._owner}/{self._repo}/pulls/{pr_number}"
        pull_response = _request_path(client, pull_path, headers=headers)
        _raise_for_live_status(
            pull_response,
            installation_id=self._installation_id,
            context="pull request fetch",
        )
        try:
            pull_payload = pull_response.json()
        except ValueError as exc:
            raise ConnectorError("malformed GitHub pull response") from exc
        if not isinstance(pull_payload, dict) or "title" not in pull_payload:
            raise ConnectorError("malformed GitHub pull response")
        files_payload = self._fetch_files(client, pr_number)
        fixture_payload = _github_pull_to_fixture_payload(pull_payload, files_payload)
        return parse_fixture_payload(fixture_payload)


def fetch_pr(
    spec: PullRequestConnectorSpec,
    *,
    access_token: SecretStr | None = None,
    transport: httpx.BaseTransport | None = None,
) -> PullRequestEvidence:
    if spec.mode == "live":
        if spec.pr_number is None or spec.pr_number <= 0:
            raise ConnectorError("pr_number is required for live PR fetch")
        if access_token is None:
            raise ConnectorError("access_token is required for live PR fetch")
        client = GitHubPullRequestClient.from_spec(
            spec,
            access_token=access_token,
            transport=transport,
        )
        return client.fetch(spec.pr_number)
    path = _resolve_fixture_path(spec)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_fixture_payload(payload)
