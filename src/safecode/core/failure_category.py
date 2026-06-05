"""Experimental runtime failure categories for debugging surfaces."""

from __future__ import annotations

from enum import StrEnum


class FailureCategory(StrEnum):
    """Experimental runtime-wide failure category values."""

    MODEL_OUTPUT_INVALID = "model_output_invalid"
    PATCH_PARSE_FAILED = "patch_parse_failed"
    PATCH_APPLY_CONFLICT = "patch_apply_conflict"
    COMMAND_TIMEOUT = "command_timeout"
    COMMAND_BLOCKED_BY_POLICY = "command_blocked_by_policy"
    NETWORK_DISABLED = "network_disabled"
    PROVIDER_AUTH_FAILED = "provider_auth_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    DEPENDENCY_MISSING = "dependency_missing"
    SANDBOX_PREFLIGHT_FAILED = "sandbox_preflight_failed"
    INTERRUPTED = "interrupted"
    LOOP_NO_PROGRESS = "loop_no_progress"
    LOOP_STUCK = "loop_stuck"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNKNOWN = "unknown"

    @property
    def next_command(self) -> str:
        """Return the suggested next command for this failure category."""
        return SUGGESTED_COMMAND_BY_CATEGORY.get(self.value, SUGGESTED_COMMAND_BY_CATEGORY[FailureCategory.UNKNOWN.value])


SUGGESTED_COMMAND_BY_CATEGORY: dict[str, str] = {
    FailureCategory.MODEL_OUTPUT_INVALID.value: "sac logs show --level error --traceback",
    FailureCategory.PATCH_PARSE_FAILED.value: "sac edit --retry-from-last-failure \"<task>\"",
    FailureCategory.PATCH_APPLY_CONFLICT.value: "sac apply",
    FailureCategory.COMMAND_TIMEOUT.value: "sac debug last-failure",
    FailureCategory.COMMAND_BLOCKED_BY_POLICY.value: "sac run \"<command>\" --yes",
    FailureCategory.NETWORK_DISABLED.value: "sac doctor",
    FailureCategory.PROVIDER_AUTH_FAILED.value: "sac setup --wizard",
    FailureCategory.PROVIDER_UNAVAILABLE.value: "sac doctor",
    FailureCategory.DEPENDENCY_MISSING.value: "sac doctor",
    FailureCategory.SANDBOX_PREFLIGHT_FAILED.value: "sac sandbox executor-preflight <backend>",
    FailureCategory.INTERRUPTED.value: "sac resume",
    FailureCategory.LOOP_NO_PROGRESS.value: "sac status",
    FailureCategory.LOOP_STUCK.value: "sac status",
    FailureCategory.BUDGET_EXCEEDED.value: "sac task budget show",
    FailureCategory.UNKNOWN.value: "sac logs show --level error --traceback",
}


def all_failure_categories() -> tuple[str, ...]:
    """Return all experimental category values in declaration order."""
    return tuple(category.value for category in FailureCategory)


def normalize_failure_category(value: str | FailureCategory | None) -> str:
    """Return a known category value, defaulting unknown/missing input to unknown."""
    if isinstance(value, FailureCategory):
        return value.value
    if value:
        raw = str(value)
        if raw in SUGGESTED_COMMAND_BY_CATEGORY:
            return raw
        legacy_aliases = {
            "blocked_suite_command": FailureCategory.COMMAND_BLOCKED_BY_POLICY.value,
            "missing_profile": FailureCategory.DEPENDENCY_MISSING.value,
        }
        if raw in legacy_aliases:
            return legacy_aliases[raw]
    return FailureCategory.UNKNOWN.value


def suggested_command_for_category(value: str | FailureCategory | None) -> str:
    """Return the deterministic suggested command for a category."""
    return SUGGESTED_COMMAND_BY_CATEGORY[normalize_failure_category(value)]


def category_for_exception(exc: BaseException) -> str:
    """Best-effort category for common runtime exception types."""
    from safecode.patch.parser import PatchParseError
    from safecode.patch.validator import PatchValidationError

    if isinstance(exc, KeyboardInterrupt):
        return FailureCategory.INTERRUPTED.value
    if isinstance(exc, PatchParseError):
        return FailureCategory.PATCH_PARSE_FAILED.value
    if isinstance(exc, PatchValidationError):
        return FailureCategory.PATCH_APPLY_CONFLICT.value
    if isinstance(exc, TimeoutError):
        return FailureCategory.COMMAND_TIMEOUT.value
    if isinstance(exc, FileNotFoundError):
        return FailureCategory.DEPENDENCY_MISSING.value
    text = str(exc).lower()
    if "auth" in text or "api key" in text or "unauthorized" in text:
        return FailureCategory.PROVIDER_AUTH_FAILED.value
    if "network" in text and "disabled" in text:
        return FailureCategory.NETWORK_DISABLED.value
    if "provider" in text or "unavailable" in text or "rate limit" in text:
        return FailureCategory.PROVIDER_UNAVAILABLE.value
    return FailureCategory.UNKNOWN.value
