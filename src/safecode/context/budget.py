"""Context budget packing with source and truncation metadata."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

if False:  # pragma: no cover - typing only without runtime import cycle
    from safecode.config import SafeCodeConfig

# B4 fix: prose ratio was 4 (optimistic); corrected to 3.5 for mixed content.
# Code content is denser, so a separate constant provides a tighter estimate.
TOKEN_CHAR_RATIO = 3.5
_CODE_TOKEN_CHAR_RATIO = 3.2


@dataclass(frozen=True)
class ContextBudget:
    """Byte and approximate token limits for context packing."""

    max_bytes: int
    max_tokens: int | None = None

    @classmethod
    def from_max_chars(cls, max_chars: int) -> "ContextBudget":
        return cls(max_bytes=max_chars, max_tokens=math.ceil(max_chars / TOKEN_CHAR_RATIO))

    @classmethod
    def from_model_profile(cls, profile: "ModelContextProfile") -> "ContextBudget":
        max_tokens = profile.safe_input_tokens
        return cls(max_bytes=math.floor(max_tokens * TOKEN_CHAR_RATIO), max_tokens=max_tokens)


@dataclass(frozen=True)
class ModelContextProfile:
    """Approximate context-window profile for model-aware context budgets."""

    model_id: str
    context_window_tokens: int
    safe_input_ratio: float = 0.70
    compact_threshold_ratio: float = 0.60

    @property
    def safe_input_tokens(self) -> int:
        return int(self.context_window_tokens * self.safe_input_ratio)

    @classmethod
    def infer(cls, provider: str, model_id: str) -> "ModelContextProfile | None":
        provider_l = provider.lower()
        model_l = model_id.lower()
        if provider_l == "mock":
            return None
        if "deepseek" in provider_l or "deepseek" in model_l:
            return cls(model_id=model_id, context_window_tokens=64_000)
        if "claude" in model_l or provider_l == "anthropic":
            return cls(model_id=model_id, context_window_tokens=200_000)
        if "gpt-4.1" in model_l:
            return cls(model_id=model_id, context_window_tokens=128_000)
        if "gpt-4o" in model_l or provider_l in {"openai", "openai-compatible"}:
            return cls(model_id=model_id, context_window_tokens=128_000)
        return None


def effective_context_budget(config: "SafeCodeConfig") -> ContextBudget:
    """Return explicit or model-aware context budget.

    ``max_context_chars`` remains an override for tests and small local configs.
    The built-in default of 40k chars is treated as a compatibility fallback;
    when a known non-mock model is configured, the model profile can choose a
    larger safe input budget.
    """
    explicit_default = 40_000
    if config.max_context_chars != explicit_default:
        return ContextBudget.from_max_chars(config.max_context_chars)
    profile = ModelContextProfile.infer(config.llm.provider, config.llm.model)
    if profile is None:
        return ContextBudget.from_max_chars(config.max_context_chars)
    return ContextBudget.from_model_profile(profile)


@dataclass(frozen=True)
class ContextSource:
    """Metadata for one packed context source."""

    key: str
    kind: str
    bytes_used: int
    tokens_estimated: int
    truncated: bool = False
    original_bytes: int | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "bytes_used": self.bytes_used,
            "tokens_estimated": self.tokens_estimated,
            "truncated": self.truncated,
        }
        if self.original_bytes is not None:
            data["original_bytes"] = self.original_bytes
        if self.note:
            data["note"] = self.note
        return data


@dataclass
class ContextBudgetReport:
    """Summary of budget usage and truncation decisions."""

    max_bytes: int
    max_tokens: int | None
    bytes_used: int = 0
    tokens_estimated: int = 0
    sources: list[ContextSource] = field(default_factory=list)
    truncation_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_bytes": self.max_bytes,
            "max_tokens": self.max_tokens,
            "bytes_used": self.bytes_used,
            "tokens_estimated": self.tokens_estimated,
            "sources": [source.to_dict() for source in self.sources],
            "truncation_notes": list(self.truncation_notes),
        }


class ContextBudgetPacker:
    """Pack context while preserving compatibility with legacy context keys."""

    def __init__(self, budget: ContextBudget) -> None:
        self.budget = budget

    def pack(self, context: dict[str, Any]) -> tuple[dict[str, Any], ContextBudgetReport]:
        remaining = max(self.budget.max_bytes, 0)
        packed: dict[str, Any] = {}
        report = ContextBudgetReport(max_bytes=self.budget.max_bytes, max_tokens=self.budget.max_tokens)

        for key, value in context.items():
            # B17: stop adding new string/list sources once budget is exhausted.
            if remaining <= 0 and isinstance(value, (str, list)):
                report.truncation_notes.append(
                    f"{key} skipped: aggregate context budget exceeded"
                )
                packed[key] = "" if isinstance(value, str) else []
                continue

            if isinstance(value, str):
                packed_value, source, remaining = self._pack_string(key, value, remaining)
                packed[key] = packed_value
                self._record(report, source)
            elif isinstance(value, list) and key == "files":
                packed_value, source, remaining = self._pack_file_list(key, value, remaining)
                packed[key] = packed_value
                self._record(report, source)
            else:
                packed[key] = value

        report.bytes_used = sum(source.bytes_used for source in report.sources)
        report.tokens_estimated = estimate_tokens_from_bytes(report.bytes_used)
        return packed, report

    def _pack_string(self, key: str, value: str, remaining: int) -> tuple[str, ContextSource, int]:
        original_bytes = _byte_len(value)
        packed = _truncate_utf8(value, remaining)
        bytes_used = _byte_len(packed)
        truncated = bytes_used < original_bytes
        note = f"{key} truncated from {original_bytes} to {bytes_used} bytes" if truncated else None
        return (
            packed,
            ContextSource(
                key=key,
                kind="text",
                bytes_used=bytes_used,
                tokens_estimated=estimate_tokens_from_bytes(bytes_used),
                truncated=truncated,
                original_bytes=original_bytes,
                note=note,
            ),
            max(remaining - bytes_used, 0),
        )

    def _pack_file_list(self, key: str, value: list[Any], remaining: int) -> tuple[list[str], ContextSource, int]:
        packed: list[str] = []
        bytes_used = 0

        for item in value:
            text = str(item)
            cost = _byte_len(text) + 1
            if bytes_used + cost > remaining:
                break
            packed.append(text)
            bytes_used += cost

        original_bytes = sum(_byte_len(str(item)) + 1 for item in value)
        truncated = len(packed) < len(value)
        note = f"{key} truncated from {len(value)} to {len(packed)} entries" if truncated else None
        return (
            packed,
            ContextSource(
                key=key,
                kind="file_list",
                bytes_used=bytes_used,
                tokens_estimated=estimate_tokens_from_bytes(bytes_used),
                truncated=truncated,
                original_bytes=original_bytes,
                note=note,
            ),
            max(remaining - bytes_used, 0),
        )

    def _record(self, report: ContextBudgetReport, source: ContextSource) -> None:
        report.sources.append(source)
        if source.note:
            report.truncation_notes.append(source.note)


def estimate_tokens_from_bytes(byte_count: int, content_type: str = "text") -> int:
    """Return a conservative local token estimate without tokenizer dependency.

    Args:
        byte_count: number of UTF-8 bytes to estimate.
        content_type: "code" uses the denser _CODE_TOKEN_CHAR_RATIO (3.2);
                      anything else uses TOKEN_CHAR_RATIO (3.5).
    """
    if byte_count <= 0:
        return 0
    ratio = _CODE_TOKEN_CHAR_RATIO if content_type == "code" else TOKEN_CHAR_RATIO
    return math.ceil(byte_count / ratio)


def _byte_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _truncate_utf8(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")
