"""Tests for v4.17.3 Levenshtein fuzzy matching for model/provider names."""

import pytest

from safecode.llm.provider_profiles import (
    _levenshtein_distance,
    _fuzzy_match,
    _fuzzy_match_model,
    _fuzzy_match_provider,
    _collect_known_model_ids,
    ProviderProfile,
)


def test_levenshtein_identical():
    assert _levenshtein_distance("hello", "hello") == 0


def test_levenshtein_empty():
    assert _levenshtein_distance("", "abc") == 3
    assert _levenshtein_distance("abc", "") == 3


def test_levenshtein_substitution():
    assert _levenshtein_distance("cat", "bat") == 1
    assert _levenshtein_distance("kitten", "sitten") == 1


def test_levenshtein_insertion_deletion():
    assert _levenshtein_distance("flas", "flash") == 1
    assert _levenshtein_distance("flash", "flas") == 1
    assert _levenshtein_distance("abc", "abcd") == 1


def test_fuzzy_match_exact():
    result = _fuzzy_match("flash", ["flash", "pro", "deepseek-v4-flash"])
    assert result == "flash"


def test_fuzzy_match_typo():
    """Fuzzy match corrects 'deepseek-v4-falsh' -> 'deepseek-v4-flash'."""
    result = _fuzzy_match("deepseek-v4-falsh", ["deepseek-v4-flash", "deepseek-v4-pro"])
    assert result == "deepseek-v4-flash"


def test_fuzzy_match_beyond_threshold():
    """No match when distance > 2."""
    result = _fuzzy_match("completely-different", ["deepseek-v4-flash", "deepseek-v4-pro"])
    assert result is None


def test_fuzzy_match_provider():
    """Fuzzy match corrects 'deapseek' -> 'deepseek'."""
    result = _fuzzy_match_provider("deapseek")
    assert result == "deepseek"


def test_fuzzy_match_provider_unknown():
    """No match for completely unknown provider."""
    result = _fuzzy_match_provider("zzzzunknown")
    assert result is None


def test_fuzzy_match_model_with_profile():
    """Fuzzy match model against active profile aliases."""
    profile = ProviderProfile(
        name="deepseek",
        default_model="deepseek-v4-flash",
        model_aliases={"flash": "deepseek-v4-flash", "pro": "deepseek-v4-pro"},
    )
    result = _fuzzy_match_model("deepseek-v4-falsh", profile)
    assert result == "deepseek-v4-flash"


def test_collect_known_model_ids():
    """Collect known model IDs from built-in aliases and profile."""
    profile = ProviderProfile(
        name="deepseek",
        default_model="deepseek-v4-flash",
        model_aliases={"flash": "deepseek-v4-flash", "pro": "deepseek-v4-pro"},
    )
    ids = _collect_known_model_ids(profile)
    assert "deepseek-v4-flash" in ids
    assert "deepseek-v4-pro" in ids


def test_resolve_model_fuzzy_correction():
    """resolve_model corrects typos via fuzzy matching."""
    profile = ProviderProfile(
        name="deepseek",
        default_model="deepseek-v4-flash",
        model_aliases={"flash": "deepseek-v4-flash", "pro": "deepseek-v4-pro"},
    )
    resolved, suggestion = profile.resolve_model("deepseek-v4-falsh")
    assert resolved == "deepseek-v4-flash"
    assert suggestion is not None
    assert "Did you mean" in suggestion


def test_resolve_model_exact_alias():
    """resolve_model returns exact alias unchanged."""
    profile = ProviderProfile(
        name="deepseek",
        model_aliases={"flash": "deepseek-v4-flash"},
    )
    resolved, suggestion = profile.resolve_model("flash")
    assert resolved == "deepseek-v4-flash"
    assert suggestion is None
