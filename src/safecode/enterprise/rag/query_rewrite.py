"""Deterministic query rewriting for enterprise retrieval (v2.4.3)."""

from __future__ import annotations

import re

_SECURITY_SYNONYMS = {
    "sqli": "sql injection",
    "xss": "cross site scripting",
    "rce": "remote code execution",
    "secrets": "hardcoded secret credential",
}

_INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore\s+(all\s+)?(prior|previous)\s+instructions"),
    re.compile(r"(?i)system\s*:\s*"),
)


def rewrite_query(query: str) -> str:
    """Apply deterministic, non-LLM query normalization."""
    normalized = " ".join(query.strip().split())
    for pattern in _INJECTION_PATTERNS:
        normalized = pattern.sub("", normalized).strip()
    lowered = normalized.lower()
    for token, replacement in _SECURITY_SYNONYMS.items():
        lowered = re.sub(rf"\b{re.escape(token)}\b", replacement, lowered)
    return lowered.strip() or query.strip()
