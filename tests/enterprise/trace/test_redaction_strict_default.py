"""Strict trace redaction default tests."""

from safecode.enterprise.trace.redaction import (
    DEFAULT_TRACE_EXPORT_PROFILE,
    apply_profile_to_text,
    resolve_export_profile,
)


def test_default_profile_is_strict():
    assert DEFAULT_TRACE_EXPORT_PROFILE == "strict"
    assert resolve_export_profile(None, requested=None) == "strict"


def test_strict_profile_redacts_raw_prompt_and_truncates_large_fields():
    large = "a" * 3000
    redacted, changed = apply_profile_to_text("raw_prompt", "secret prompt", profile="strict")
    assert redacted == "[redacted]"
    assert changed is True
    excerpt, changed2 = apply_profile_to_text("preview", large, profile="strict")
    assert len(excerpt.encode("utf-8")) <= 2048 + 16
    assert changed2 is True
