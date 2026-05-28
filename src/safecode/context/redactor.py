"""Redact secret-like content before sending context to an LLM."""

import re


SECRET_PATTERNS = [
    re.compile(r'(?i)("?(?:api[_-]?key|secret|token|password|access[_-]?key|client[_-]?secret)"?)\s*([:=])\s*("?)[^"\s,}]+("?)'),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[a-z0-9._~+/=-]+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


def redact_secrets(text: str) -> str:
    """Replace obvious secret values with a stable placeholder."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 4:
            redacted = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]{match.group(4)}", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        else:
            replacement = "[REDACTED_PRIVATE_KEY]" if "PRIVATE KEY" in pattern.pattern else "[REDACTED]"
            redacted = pattern.sub(replacement, redacted)
    return redacted
