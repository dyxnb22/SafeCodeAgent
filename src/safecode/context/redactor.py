"""Redact secret-like content before sending context to an LLM."""

import re


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*([^\s]+)"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*:\s*([^\s]+)"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


def redact_secrets(text: str) -> str:
    """Replace obvious secret values with a stable placeholder."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED_PRIVATE_KEY]", redacted)
    return redacted
