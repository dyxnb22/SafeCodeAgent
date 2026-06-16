"""Tests for v2.5.2 failure taxonomy (failures.py) and runner integration.

Coverage:
  A. FailureCategory enum — all values present and serializable.
  B. ClassifiedFailure dataclass — frozen, as_dict round-trip.
  C. classify_replay_result — returns [] for passing results.
  D. classify_replay_result — setup category from result.error.
  E. classify_replay_result — forbidden_file_write from structured signal.
  F. classify_replay_result — command_blocked from structured signal.
  G. classify_replay_result — forbidden_file_changed from failure_reasons.
  H. classify_replay_result — validation category variants.
  I. classify_replay_result — timeout category.
  J. classify_replay_result — unknown fallback.
  K. classify_replay_result — structured signals skip duplicated string reasons.
  L. Runner integration — classified_failures populated in ReplayResult.
  M. Runner integration — passing result has empty classified_failures.
  N. Runner integration — error result classified as setup.
  O. Runner integration — forbidden_file_write classified end-to-end.
  P. Runner integration — timeout classified end-to-end.
  Q. Runner integration — validation classified end-to-end.
  R. Runner integration — forbidden_file_changed classified end-to-end.
  S. Backward compat — ReplayResult constructed without classified_failures defaults to [].
"""

from __future__ import annotations

import pytest

from safecode.eval.failures import (
    ClassifiedFailure,
    FailureCategory,
    _categorize_reason,
    classify_replay_result,
)
from safecode.eval.loader import load_fixture_from_dict
from safecode.eval.runner import ReplayResult, TaskReplayRunner, ValidationCommandResult


# ── helpers ───────────────────────────────────────────────────────────────


def _passing_result(**kwargs) -> ReplayResult:
    defaults = dict(
        fixture_name="test",
        passed=True,
        failure_reasons=[],
        validation_details=[],
        observed_changed_files=[],
        workspace_diff="",
        network_intent="denied",
        forbidden_commands_violated=[],
        forbidden_file_writes_violated=[],
        audit_events_status="ok",
    )
    defaults.update(kwargs)
    return ReplayResult(**defaults)


def _failing_result(**kwargs) -> ReplayResult:
    defaults = dict(
        fixture_name="test",
        passed=False,
        failure_reasons=["Something failed."],
        validation_details=[],
        observed_changed_files=[],
        workspace_diff="",
        network_intent="denied",
        forbidden_commands_violated=[],
        forbidden_file_writes_violated=[],
        audit_events_status="ok",
    )
    defaults.update(kwargs)
    return ReplayResult(**defaults)


def _fixture(
    *,
    name: str = "test",
    goal: str = "Do something",
    repo_files: dict | None = None,
    setup_commands: list[str] | None = None,
    validation_commands: list[str] | None = None,
    expected_changed_files: list[str] | None = None,
    forbidden_changed_files: list[str] | None = None,
    safety: dict | None = None,
    expected_exit_code: int | None = None,
    expected_output_contains: list[str] | None = None,
    timeout_seconds: int = 30,
):
    repo: dict = {"kind": "inline", "files": repo_files or {}}
    if setup_commands:
        repo["setup_commands"] = setup_commands

    expected: dict = {"kind": "any"}
    if expected_exit_code is not None:
        expected["expected_exit_code"] = expected_exit_code
    if expected_output_contains:
        expected["expected_output_contains"] = expected_output_contains

    d: dict = {
        "name": name,
        "goal": goal,
        "repo": repo,
        "expected": expected,
        "safety": safety or {},
        "timeout_seconds": timeout_seconds,
    }
    if validation_commands is not None:
        d["validation_commands"] = validation_commands
    if expected_changed_files is not None:
        d["expected_changed_files"] = expected_changed_files
    if forbidden_changed_files is not None:
        d["forbidden_changed_files"] = forbidden_changed_files
    return load_fixture_from_dict(d)


def _runner() -> TaskReplayRunner:
    return TaskReplayRunner()


# ── A. FailureCategory enum ───────────────────────────────────────────────


class TestFailureCategoryEnum:
    def test_all_required_categories_present(self):
        required = {
            "context_miss", "patch_parse", "validation", "command_blocked",
            "forbidden_file_write", "forbidden_file_changed", "setup",
            "timeout", "model_error", "audit_unverified", "unknown",
        }
        actual = {c.value for c in FailureCategory}
        assert required <= actual

    def test_categories_are_strings(self):
        for cat in FailureCategory:
            assert isinstance(cat.value, str)
            assert len(cat.value) > 0

    def test_category_is_str_subclass(self):
        assert issubclass(FailureCategory, str)

    def test_category_json_serializable(self):
        import json
        # StrEnum values serialize directly as strings
        for cat in FailureCategory:
            assert json.dumps(cat.value)  # no exception

    def test_category_comparison(self):
        assert FailureCategory.validation == "validation"
        assert FailureCategory.setup == "setup"
        assert FailureCategory.unknown == "unknown"


# ── B. ClassifiedFailure dataclass ────────────────────────────────────────


class TestClassifiedFailure:
    def test_frozen(self):
        cf = ClassifiedFailure(category=FailureCategory.setup, reason="err")
        with pytest.raises((AttributeError, TypeError)):
            cf.reason = "other"  # type: ignore[misc]

    def test_default_detail_none(self):
        cf = ClassifiedFailure(category=FailureCategory.unknown, reason="x")
        assert cf.detail is None

    def test_as_dict_structure(self):
        cf = ClassifiedFailure(
            category=FailureCategory.forbidden_file_write,
            reason="Forbidden file write detected: '.env'",
            detail=".env",
        )
        d = cf.as_dict()
        assert d["category"] == "forbidden_file_write"
        assert d["reason"] == "Forbidden file write detected: '.env'"
        assert d["detail"] == ".env"

    def test_as_dict_null_detail(self):
        cf = ClassifiedFailure(category=FailureCategory.validation, reason="expected x")
        assert cf.as_dict()["detail"] is None

    def test_equality(self):
        a = ClassifiedFailure(category=FailureCategory.timeout, reason="timed out")
        b = ClassifiedFailure(category=FailureCategory.timeout, reason="timed out")
        assert a == b


# ── C. classify_replay_result — passing result ────────────────────────────


class TestClassifyPassingResult:
    def test_passing_returns_empty(self):
        result = _passing_result()
        assert classify_replay_result(result) == []

    def test_passing_result_with_no_violations(self):
        result = _passing_result(forbidden_commands_violated=[], forbidden_file_writes_violated=[])
        assert classify_replay_result(result) == []


# ── D. setup category from result.error ───────────────────────────────────


class TestClassifySetupFromError:
    def test_error_result_classified_as_setup(self):
        result = _failing_result(error="Local repo path does not exist: /tmp/missing")
        classified = classify_replay_result(result)
        assert len(classified) == 1
        assert classified[0].category == FailureCategory.setup

    def test_error_result_reason_matches_error(self):
        err = "Workspace materialisation failed: some OS error"
        result = _failing_result(error=err)
        classified = classify_replay_result(result)
        assert classified[0].reason == err

    def test_error_result_short_circuits(self):
        # When error is set, only one ClassifiedFailure is returned even if
        # failure_reasons also has entries.
        result = _failing_result(
            error="Workspace materialisation failed: oops",
            failure_reasons=["Workspace materialisation failed: oops", "other reason"],
            forbidden_file_writes_violated=[".env"],
        )
        classified = classify_replay_result(result)
        assert len(classified) == 1
        assert classified[0].category == FailureCategory.setup


# ── E. forbidden_file_write from structured signal ────────────────────────


class TestClassifyForbiddenFileWrite:
    def test_structured_signal_classified(self):
        result = _failing_result(
            forbidden_file_writes_violated=[".env"],
            failure_reasons=["Safety violation: forbidden file write '.env' was detected."],
        )
        classified = classify_replay_result(result)
        fw = [c for c in classified if c.category == FailureCategory.forbidden_file_write]
        assert len(fw) == 1
        assert fw[0].detail == ".env"

    def test_multiple_violations(self):
        result = _failing_result(
            forbidden_file_writes_violated=[".env", "secrets.txt"],
            failure_reasons=[
                "Safety violation: forbidden file write '.env' was detected.",
                "Safety violation: forbidden file write 'secrets.txt' was detected.",
            ],
        )
        classified = classify_replay_result(result)
        fw = [c for c in classified if c.category == FailureCategory.forbidden_file_write]
        assert len(fw) == 2
        details = {c.detail for c in fw}
        assert details == {".env", "secrets.txt"}

    def test_structured_reason_string_not_duplicated(self):
        # The reason string "Safety violation: forbidden file write..." should NOT
        # produce an additional ClassifiedFailure from the failure_reasons loop.
        result = _failing_result(
            forbidden_file_writes_violated=[".env"],
            failure_reasons=["Safety violation: forbidden file write '.env' was detected."],
        )
        classified = classify_replay_result(result)
        fw = [c for c in classified if c.category == FailureCategory.forbidden_file_write]
        assert len(fw) == 1  # only one, from the structured signal

    def test_detail_matches_pattern(self):
        result = _failing_result(
            forbidden_file_writes_violated=["credentials.json"],
            failure_reasons=["Safety violation: forbidden file write 'credentials.json' was detected."],
        )
        classified = classify_replay_result(result)
        fw = classified[0]
        assert fw.detail == "credentials.json"


# ── F. command_blocked from structured signal ─────────────────────────────


class TestClassifyCommandBlocked:
    def test_command_blocked_classified(self):
        result = _failing_result(
            forbidden_commands_violated=["curl"],
            failure_reasons=[
                "Safety violation: forbidden command pattern 'curl' observed in validation commands."
            ],
        )
        classified = classify_replay_result(result)
        cb = [c for c in classified if c.category == FailureCategory.command_blocked]
        assert len(cb) == 1
        assert cb[0].detail == "curl"

    def test_structured_reason_not_duplicated_for_command(self):
        result = _failing_result(
            forbidden_commands_violated=["wget"],
            failure_reasons=[
                "Safety violation: forbidden command pattern 'wget' observed in validation commands."
            ],
        )
        classified = classify_replay_result(result)
        cb = [c for c in classified if c.category == FailureCategory.command_blocked]
        assert len(cb) == 1


# ── G. forbidden_file_changed ─────────────────────────────────────────────


class TestClassifyForbiddenFileChanged:
    def test_forbidden_file_changed_classified(self):
        reason = "Forbidden file 'secret.env' was changed (forbidden_changed_files)."
        result = _failing_result(failure_reasons=[reason])
        classified = classify_replay_result(result)
        assert len(classified) == 1
        assert classified[0].category == FailureCategory.forbidden_file_changed

    def test_forbidden_file_changed_reason_preserved(self):
        reason = "Forbidden file 'b.txt' was changed (forbidden_changed_files)."
        result = _failing_result(failure_reasons=[reason])
        classified = classify_replay_result(result)
        assert classified[0].reason == reason


# ── H. validation category ────────────────────────────────────────────────


class TestClassifyValidation:
    @pytest.mark.parametrize("reason", [
        "Validation command exited with code 1: 'false'",
        "Validation command timed out after 1s: 'sleep 10'",
        "Expected last validation command exit code 0, got 1.",
        "Expected output to contain 'needle' but it was not found.",
        "Expected workspace diff to contain 'patch' but it was not found.",
        "Expected file 'calc.py' to be changed but it was not.",
        "Expected changed file 'main.py' (expected_changed_files) was not changed.",
    ])
    def test_validation_reason_classified(self, reason):
        # Exclude the timeout case from _categorize_reason since "timed out" in
        # "Validation command timed out" maps to timeout, not validation.
        if "timed out" in reason.lower():
            # timeout takes priority since "Setup command" not present
            category = FailureCategory.timeout
        else:
            category = FailureCategory.validation
        assert _categorize_reason(reason) == category

    def test_exit_code_reason_is_validation(self):
        reason = "Expected last validation command exit code 1, got 0."
        assert _categorize_reason(reason) == FailureCategory.validation

    def test_output_contains_reason_is_validation(self):
        reason = "Expected output to contain 'hello' but it was not found."
        assert _categorize_reason(reason) == FailureCategory.validation


# ── I. timeout category ───────────────────────────────────────────────────


class TestClassifyTimeout:
    def test_validation_timeout_classified(self):
        reason = "Validation command timed out after 1s: 'sleep 10'"
        assert _categorize_reason(reason) == FailureCategory.timeout

    def test_setup_timeout_classified_as_setup_not_timeout(self):
        # "Setup command" prefix takes priority over "timed out"
        reason = "Setup command timed out after 30s: 'sleep 999'"
        assert _categorize_reason(reason) == FailureCategory.setup


# ── J. unknown fallback ───────────────────────────────────────────────────


class TestClassifyUnknown:
    def test_unrecognised_reason_is_unknown(self):
        assert _categorize_reason("Some completely novel failure message.") == FailureCategory.unknown

    def test_empty_reason_is_unknown(self):
        assert _categorize_reason("") == FailureCategory.unknown


# ── K. structured signals skip duplicated string reasons ──────────────────


class TestNoDuplication:
    def test_mixed_structured_and_unstructured(self):
        result = _failing_result(
            forbidden_file_writes_violated=[".env"],
            failure_reasons=[
                "Safety violation: forbidden file write '.env' was detected.",
                "Expected output to contain 'hello' but it was not found.",
            ],
        )
        classified = classify_replay_result(result)
        categories = [c.category for c in classified]
        assert FailureCategory.forbidden_file_write in categories
        assert FailureCategory.validation in categories
        # forbidden_file_write should appear exactly once (from structured signal)
        assert categories.count(FailureCategory.forbidden_file_write) == 1

    def test_command_blocked_and_validation_mixed(self):
        result = _failing_result(
            forbidden_commands_violated=["curl"],
            failure_reasons=[
                "Safety violation: forbidden command pattern 'curl' observed in validation commands.",
                "Expected output to contain 'OK' but it was not found.",
            ],
        )
        classified = classify_replay_result(result)
        categories = [c.category for c in classified]
        assert FailureCategory.command_blocked in categories
        assert FailureCategory.validation in categories
        assert categories.count(FailureCategory.command_blocked) == 1


# ── L. Runner integration — classified_failures populated ─────────────────


class TestRunnerClassifiedFailuresPopulated:
    def test_failing_result_has_classified_failures(self):
        fix = _fixture(
            repo_files={"f.txt": "x"},
            expected_output_contains=["IMPOSSIBLE"],
            validation_commands=["echo something"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert len(result.classified_failures) > 0

    def test_classified_failures_are_classified_failure_instances(self):
        fix = _fixture(
            repo_files={},
            validation_commands=["false"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        for cf in result.classified_failures:
            assert isinstance(cf, ClassifiedFailure)


# ── M. Runner integration — passing result has empty classified_failures ───


class TestRunnerPassingEmpty:
    def test_passing_result_empty_classified_failures(self):
        fix = _fixture(repo_files={})
        result = _runner().run(fix)
        assert result.passed is True
        assert result.classified_failures == []

    def test_passing_validation_command_empty_classified(self):
        fix = _fixture(validation_commands=["true"])
        result = _runner().run(fix)
        assert result.classified_failures == []


# ── N. Runner integration — error result classified as setup ──────────────


class TestRunnerErrorResultSetup:
    def test_nonexistent_local_path_classified_as_setup(self):
        d = {
            "name": "err-test",
            "goal": "check",
            "repo": {"kind": "local", "path": "/nonexistent/path/99999"},
            "expected": {"kind": "any"},
            "safety": {},
        }
        fix = load_fixture_from_dict(d)
        result = _runner().run(fix)
        assert result.passed is False
        assert len(result.classified_failures) == 1
        assert result.classified_failures[0].category == FailureCategory.setup


# ── O. Runner integration — forbidden_file_write end-to-end ───────────────


class TestRunnerForbiddenFileWriteE2E:
    def test_forbidden_write_classified_end_to_end(self):
        fix = _fixture(
            repo_files={},
            setup_commands=["echo SECRET=1 > .env"],
            safety={"forbidden_file_writes": [".env"]},
        )
        result = _runner().run(fix)
        assert result.passed is False
        fw = [c for c in result.classified_failures if c.category == FailureCategory.forbidden_file_write]
        assert len(fw) >= 1
        assert fw[0].detail == ".env"


# ── P. Runner integration — timeout classified end-to-end ─────────────────


@pytest.mark.slow
@pytest.mark.timeout
class TestRunnerTimeoutE2E:
    def test_validation_timeout_classified_as_timeout(self):
        fix = _fixture(
            validation_commands=["sleep 10"],
            timeout_seconds=1,
        )
        result = _runner().run(fix)
        assert result.passed is False
        timeout_failures = [c for c in result.classified_failures if c.category == FailureCategory.timeout]
        assert len(timeout_failures) >= 1


# ── Q. Runner integration — validation classified end-to-end ──────────────


class TestRunnerValidationE2E:
    def test_output_contains_miss_classified_as_validation(self):
        fix = _fixture(
            validation_commands=["echo hello"],
            expected_output_contains=["MISSING_NEEDLE"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        val = [c for c in result.classified_failures if c.category == FailureCategory.validation]
        assert len(val) >= 1

    def test_exit_code_mismatch_classified_as_validation(self):
        fix = _fixture(
            validation_commands=["true"],
            expected_exit_code=1,
        )
        result = _runner().run(fix)
        assert result.passed is False
        val = [c for c in result.classified_failures if c.category == FailureCategory.validation]
        assert len(val) >= 1


# ── R. Runner integration — forbidden_file_changed end-to-end ─────────────


class TestRunnerForbiddenFileChangedE2E:
    def test_forbidden_changed_file_classified(self):
        fix = _fixture(
            repo_files={"secret.env": "KEY=original"},
            setup_commands=["echo KEY=leaked > secret.env"],
            forbidden_changed_files=["secret.env"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        fc = [c for c in result.classified_failures if c.category == FailureCategory.forbidden_file_changed]
        assert len(fc) >= 1


# ── S. Backward compat — default classified_failures ─────────────────────


class TestBackwardCompat:
    def test_replay_result_without_classified_failures_defaults_empty(self):
        r = ReplayResult(
            fixture_name="compat",
            passed=True,
            failure_reasons=[],
            validation_details=[],
            observed_changed_files=[],
            workspace_diff="",
            network_intent="denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="ok",
        )
        assert r.classified_failures == []

    def test_existing_fields_still_accessible(self):
        r = ReplayResult(
            fixture_name="compat",
            passed=False,
            failure_reasons=["x"],
            validation_details=[
                ValidationCommandResult(
                    command="false", exit_code=1, stdout="", stderr="", passed=False
                )
            ],
            observed_changed_files=["a.py"],
            workspace_diff="--- a\n+++ b\n",
            network_intent="denied",
            forbidden_commands_violated=["rm"],
            forbidden_file_writes_violated=[".env"],
            audit_events_status="ok",
        )
        assert r.fixture_name == "compat"
        assert r.failure_reasons == ["x"]
        assert r.forbidden_commands_violated == ["rm"]
        assert r.forbidden_file_writes_violated == [".env"]
        assert r.classified_failures == []
