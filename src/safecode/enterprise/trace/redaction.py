"""Strict trace export redaction profiles.

中文模块说明：trace/timeline 导出的 redaction profile（strict/standard/debug）。
- 架构位置：Observability 导出与 console 显示对齐（console 有平行实现）。
- 安全不变量：strict 为默认；debug 需策略解锁；tool_input 等字段默认隐藏。
- 学习路径：对照 ``console/src/lib/redaction/display.ts``。
"""

from __future__ import annotations

from typing import Literal

from safecode.context.redactor import redact_secrets
from safecode.enterprise.policy.models import PolicySnapshot
from safecode.enterprise.policy.resolver import policy_bool

TraceExportProfile = Literal["strict", "standard", "debug"]
DEFAULT_TRACE_EXPORT_PROFILE: TraceExportProfile = "strict"
MAX_STRICT_FIELD_BYTES = 2048


class DebugTraceNotAllowed(Exception):
    """Raised when debug trace export is requested without policy unlock."""


def resolve_export_profile(
    snapshot: PolicySnapshot | None,
    *,
    requested: str | None = None,
) -> TraceExportProfile:
    profile = (requested or DEFAULT_TRACE_EXPORT_PROFILE).strip().lower()
    if profile not in {"strict", "standard", "debug"}:
        profile = DEFAULT_TRACE_EXPORT_PROFILE
    if profile == "debug":
        if snapshot is None or not policy_bool(snapshot, "allow_debug_traces", default=False):
            raise DebugTraceNotAllowed(
                "debug trace export requires org policy allow_debug_traces=true"
            )
    return profile  # type: ignore[return-value]


def apply_profile_to_text(
    field_name: str,
    value: str,
    *,
    profile: TraceExportProfile,
) -> tuple[str, bool]:
    redacted = redact_secrets(value)
    changed = redacted != value
    if profile == "strict":
        if field_name in {"raw_prompt", "raw_model_prompt", "file_content"}:
            return "[redacted]", True
        if len(redacted.encode("utf-8")) > MAX_STRICT_FIELD_BYTES:
            redacted = redacted[:MAX_STRICT_FIELD_BYTES] + "…[truncated]"
            changed = True
        elif field_name.startswith("tool_input"):
            changed = True
        return redacted, changed
    if profile == "standard":
        limit = 2048 if field_name != "file_content" else 1024
        if len(redacted.encode("utf-8")) > limit:
            redacted = redacted[:limit] + "…[truncated]"
            changed = True
        return redacted, changed
    limit = 8192
    if len(redacted.encode("utf-8")) > limit:
        redacted = redacted[:limit] + "…[truncated]"
        changed = True
    return redacted, changed


def apply_profile_to_payload(
    payload: dict[str, object],
    *,
    profile: TraceExportProfile,
) -> tuple[dict[str, object], bool]:
    if profile == "strict":
        profile = "strict"
    output: dict[str, object] = {}
    changed = False
    for key, value in payload.items():
        if isinstance(value, str):
            new_value, field_changed = apply_profile_to_text(key, value, profile=profile)
            output[key] = new_value
            changed = changed or field_changed
        else:
            output[key] = value
    return output, changed
