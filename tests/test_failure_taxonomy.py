"""Tests for experimental v4.7 runtime failure taxonomy."""

from __future__ import annotations

import json

from safecode.core.failure_category import (
    SUGGESTED_COMMAND_BY_CATEGORY,
    FailureCategory,
    all_failure_categories,
    normalize_failure_category,
    suggested_command_for_category,
)
from safecode.logs.runtime import RuntimeLogEvent, RuntimeLogger


def test_every_category_has_suggested_command() -> None:
    categories = all_failure_categories()
    assert categories == tuple(category.value for category in FailureCategory)
    assert set(SUGGESTED_COMMAND_BY_CATEGORY) == set(categories)
    assert all(SUGGESTED_COMMAND_BY_CATEGORY[category].startswith("sac ") for category in categories)


def test_suggested_command_mapping_is_deterministic() -> None:
    assert suggested_command_for_category("command_timeout") == SUGGESTED_COMMAND_BY_CATEGORY["command_timeout"]
    assert suggested_command_for_category("not-a-real-category") == SUGGESTED_COMMAND_BY_CATEGORY["unknown"]


def test_legacy_category_aliases_normalize() -> None:
    assert normalize_failure_category("blocked_suite_command") == "command_blocked_by_policy"
    assert normalize_failure_category("missing_profile") == "dependency_missing"


def test_runtime_log_event_accepts_older_log_without_failure_category() -> None:
    event = RuntimeLogEvent(
        timestamp="2026-01-01T00:00:00+00:00",
        level="error",
        component="test",
        message="old log",
    )
    assert event.failure_category is None


def test_runtime_logger_reads_old_and_new_log_lines(tmp_path) -> None:
    log_path = tmp_path / ".sac" / "logs" / "runtime.jsonl"
    log_path.parent.mkdir(parents=True)
    old_event = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "level": "error",
        "component": "old",
        "message": "legacy",
        "details": {},
    }
    new_event = {
        **old_event,
        "timestamp": "2026-01-01T00:00:01+00:00",
        "component": "new",
        "failure_category": "command_timeout",
    }
    log_path.write_text(json.dumps(old_event) + "\n" + json.dumps(new_event) + "\n", encoding="utf-8")
    events = RuntimeLogger(tmp_path).read_recent(limit=10)
    assert [event.component for event in events] == ["old", "new"]
    assert events[0].failure_category is None
    assert events[1].failure_category == "command_timeout"


def test_runtime_logger_redacts_secret_values(tmp_path) -> None:
    RuntimeLogger(tmp_path).write(
        "error",
        "test",
        "token=s3cr3t",
        failure_category="unknown",
        details={"command": "echo api_key=abcd"},
    )
    raw = (tmp_path / ".sac" / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    assert "s3cr3t" not in raw
    assert "abcd" not in raw
