"""Deterministic redaction for enterprise demo transcripts."""

from __future__ import annotations

import re

_RUN_ID = re.compile(r"run-[a-zA-Z0-9_-]{8,64}")
_APPROVAL_ID = re.compile(r"approval-run-[a-zA-Z0-9_-]+")
_GRANT_ID = re.compile(r"grant-[a-zA-Z0-9_-]+")
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_ABSOLUTE_PATH = re.compile(
    r"(?:/Users/[^\s\])\"']+|/home/[^\s\])\"']+|/var/[^\s\])\"']+|"
    r"/private/[^\s\])\"']+)"
)
_HOSTNAME = re.compile(
    r"\b[a-zA-Z0-9][a-zA-Z0-9.-]*\.(?:local|internal|corp|lan)\b"
)
_BEARER = re.compile(r"Bearer\s+\S+")
_SECRET_LITERAL = re.compile(
    r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"]+['\"]"
)
_SHA256 = re.compile(r"\b[a-f0-9]{64}\b")
_GITHUB_TOKEN = re.compile(r"ghp_[A-Za-z0-9]{20,}")


def redact_transcript(text: str) -> str:
    """Replace volatile or sensitive transcript fields with stable placeholders."""
    redacted = text
    redacted = _BEARER.sub("Bearer <redacted-secret>", redacted)
    redacted = _GITHUB_TOKEN.sub("<redacted-secret>", redacted)
    redacted = _SECRET_LITERAL.sub(r"\1: <redacted-secret>", redacted)
    redacted = _TIMESTAMP.sub("<timestamp>", redacted)
    redacted = _ISO_DATE.sub("<date>", redacted)
    redacted = _APPROVAL_ID.sub("<approval-id>", redacted)
    redacted = _GRANT_ID.sub("<grant-id>", redacted)
    redacted = _RUN_ID.sub("<run-id>", redacted)
    redacted = _ABSOLUTE_PATH.sub("<path>", redacted)
    redacted = _HOSTNAME.sub("<hostname>", redacted)
    redacted = _SHA256.sub("<hash>", redacted)
    return redacted
