"""Tests for v2.9.0 agent-loop-fixture-expansion.

Verifies:
- default_loop_fixtures() returns exactly six fixtures.
- All six fixtures have unique names.
- All six fixtures run to completion without exceptions.
- Typed failure categories are correct for known failure modes.
- ClassifiedLoopFailure.as_dict() is serializable.
- LoopFailureCategory enum values are stable.
- sac eval --mode loop mentions all six fixture names.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from safecode.agent.schemas import AgentPatchResponse, AgentStopForUserResponse, AgentToolIntentResponse
from safecode.agent.tools import ToolIntent
from safecode.cli import app
from safecode.eval.loop_runner import (
    ClassifiedLoopFailure,
    LLMContractViolation,
    LoopEvalFixture,
    LoopEvalResult,
    LoopFailureCategory,
    LoopModeEvalRunner,
    RecoverableContractFailure,
    ScriptedLLMClient,
    ScriptedStep,
    _classify_loop_result,
    default_loop_fixtures,
)

runner = CliRunner()

EXPECTED_FIXTURE_NAMES = {
    "docs-edit",
    "python-function-fix",
    "config-update-fix",
    "test-assertion-fix",
    "shell-readonly-check",
    "import-cleanup",
}


# ── Fixture loading ───────────────────────────────────────────────────────


class TestFixtureLoading:
    def test_default_fixtures_count(self):
        assert len(default_loop_fixtures()) == 6

    def test_default_fixtures_names(self):
        names = {f.name for f in default_loop_fixtures()}
        assert names == EXPECTED_FIXTURE_NAMES

    def test_all_fixtures_have_goal(self):
        for f in default_loop_fixtures():
            assert f.goal, f"Fixture {f.name!r} has no goal"

    def test_all_fixtures_have_steps(self):
        for f in default_loop_fixtures():
            assert f.scripted_steps, f"Fixture {f.name!r} has no scripted steps"

    def test_all_fixtures_have_files(self):
        for f in default_loop_fixtures():
            assert f.files, f"Fixture {f.name!r} has no files"

    def test_config_toml_present_in_all_fixtures(self):
        for f in default_loop_fixtures():
            assert ".sac/config.toml" in f.files, f"Fixture {f.name!r} missing .sac/config.toml"


# ── Execution count ───────────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.eval
class TestFixtureExecutionCount:
    def test_run_all_returns_six_results(self):
        fixtures = default_loop_fixtures()
        results = LoopModeEvalRunner().run_all(fixtures)
        assert len(results) == 6

    def test_run_all_result_names_match_fixtures(self):
        fixtures = default_loop_fixtures()
        results = LoopModeEvalRunner().run_all(fixtures)
        result_names = {r.fixture_name for r in results}
        fixture_names = {f.name for f in fixtures}
        assert result_names == fixture_names

    def test_all_fixture_results_have_bool_passed(self):
        for r in LoopModeEvalRunner().run_all(default_loop_fixtures()):
            assert isinstance(r.passed, bool), f"Fixture {r.fixture_name!r} passed is not bool"

    def test_patch_fixtures_pass(self):
        patch_fixture_names = {
            "docs-edit",
            "python-function-fix",
            "config-update-fix",
            "test-assertion-fix",
            "import-cleanup",
        }
        runner_inst = LoopModeEvalRunner()
        for f in default_loop_fixtures():
            if f.name in patch_fixture_names:
                r = runner_inst.run_fixture(f)
                assert r.passed, f"Fixture {f.name!r} failed: {r.failure_reasons}"
                assert not r.violations, f"Fixture {f.name!r} has violations"

    def test_shell_readonly_check_passes(self):
        f = next(f for f in default_loop_fixtures() if f.name == "shell-readonly-check")
        r = LoopModeEvalRunner().run_fixture(f)
        assert r.passed, f"shell-readonly-check failed: {r.failure_reasons}"
        assert not r.violations

    def test_shell_readonly_check_not_pending_patch(self):
        f = next(f for f in default_loop_fixtures() if f.name == "shell-readonly-check")
        assert not f.expected_pending_patch


# ── Typed failure categories ──────────────────────────────────────────────


class TestLoopFailureCategory:
    def test_enum_values_stable(self):
        assert LoopFailureCategory.contract_violation == "contract_violation"
        assert LoopFailureCategory.patch_missing == "patch_missing"
        assert LoopFailureCategory.patch_content_mismatch == "patch_content_mismatch"
        assert LoopFailureCategory.loop_error == "loop_error"
        assert LoopFailureCategory.unknown == "unknown"

    def test_str_subclass(self):
        assert isinstance(LoopFailureCategory.contract_violation, str)

    def test_five_categories(self):
        assert len(list(LoopFailureCategory)) == 5


class TestClassifiedLoopFailure:
    def test_frozen(self):
        cf = ClassifiedLoopFailure(
            category=LoopFailureCategory.unknown,
            reason="some reason",
        )
        with pytest.raises((AttributeError, TypeError)):
            cf.reason = "changed"  # type: ignore[misc]

    def test_as_dict_keys(self):
        cf = ClassifiedLoopFailure(
            category=LoopFailureCategory.patch_missing,
            reason="No pending patch found.",
        )
        d = cf.as_dict()
        assert set(d.keys()) == {"category", "reason"}

    def test_as_dict_category_is_string(self):
        cf = ClassifiedLoopFailure(
            category=LoopFailureCategory.contract_violation,
            reason="Scripted violation",
        )
        d = cf.as_dict()
        assert isinstance(d["category"], str)
        assert d["category"] == "contract_violation"


class TestClassifyLoopResult:
    def test_passing_result_returns_empty(self):
        result = LoopEvalResult(fixture_name="x", passed=True)
        assert _classify_loop_result(result) == []

    def test_violation_classified_as_contract_violation(self):
        v = LLMContractViolation(step=0, method="choose_tool", message="exhausted")
        result = LoopEvalResult(
            fixture_name="x",
            passed=False,
            failure_reasons=["LLM contract violation in choose_tool: exhausted"],
            violations=[v],
        )
        classified = _classify_loop_result(result)
        assert any(c.category == LoopFailureCategory.contract_violation for c in classified)

    def test_patch_missing_classified(self):
        result = LoopEvalResult(
            fixture_name="x",
            passed=False,
            failure_reasons=["Expected a pending patch (type=patch + pending_patch_path) but got type='', path=''"],
        )
        classified = _classify_loop_result(result)
        assert any(c.category == LoopFailureCategory.patch_missing for c in classified)

    def test_patch_content_mismatch_classified(self):
        result = LoopEvalResult(
            fixture_name="x",
            passed=False,
            failure_reasons=["Pending patch missing expected fragment: 'hello'"],
        )
        classified = _classify_loop_result(result)
        assert any(c.category == LoopFailureCategory.patch_content_mismatch for c in classified)

    def test_loop_error_classified(self):
        result = LoopEvalResult(
            fixture_name="x",
            passed=False,
            failure_reasons=["Loop raised unexpected exception: ValueError: oops"],
        )
        classified = _classify_loop_result(result)
        assert any(c.category == LoopFailureCategory.loop_error for c in classified)

    def test_unknown_failure_classified(self):
        result = LoopEvalResult(
            fixture_name="x",
            passed=False,
            failure_reasons=["Something unexpected went wrong"],
        )
        classified = _classify_loop_result(result)
        assert any(c.category == LoopFailureCategory.unknown for c in classified)

    def test_no_failure_reasons_gets_unknown(self):
        result = LoopEvalResult(fixture_name="x", passed=False)
        classified = _classify_loop_result(result)
        assert len(classified) == 1
        assert classified[0].category == LoopFailureCategory.unknown

    def test_classified_failures_populated_on_result(self):
        f = next(f for f in default_loop_fixtures() if f.name == "docs-edit")
        r = LoopModeEvalRunner().run_fixture(f)
        assert r.passed
        assert r.classified_failures == []

    def test_classified_failures_populated_on_failing_result(self):
        """A fixture that exhausts the script should have classified failures."""
        empty_fixture = LoopEvalFixture(
            name="empty-script",
            goal="Do something",
            files={".sac/config.toml": '[llm]\nprovider = "mock"\n'},
            scripted_steps=[],
            expected_pending_patch=False,
        )
        r = LoopModeEvalRunner().run_fixture(empty_fixture)
        if not r.passed:
            assert r.classified_failures, "Failed result should have classified_failures"


# ── RecoverableContractFailure is importable ──────────────────────────────


class TestRecoverableContractFailureType:
    def test_frozen(self):
        rcf = RecoverableContractFailure(step=0, method="choose_tool", message="scripted")
        with pytest.raises((AttributeError, TypeError)):
            rcf.message = "changed"  # type: ignore[misc]

    def test_distinct_from_llm_contract_violation(self):
        rcf = RecoverableContractFailure(step=0, method="choose_tool", message="scripted")
        v = LLMContractViolation(step=0, method="choose_tool", message="exhausted")
        assert type(rcf) is not type(v)


# ── CLI shows all six fixture names ──────────────────────────────────────


@pytest.mark.slow
@pytest.mark.eval
class TestEvalLoopModeCLISixFixtures:
    def test_eval_loop_mode_shows_all_six_names(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "loop"], catch_exceptions=False)
        for name in EXPECTED_FIXTURE_NAMES:
            assert name in result.output, f"Fixture name {name!r} not in CLI output"

    def test_eval_loop_mode_exits_zero(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "loop"], catch_exceptions=False)
        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
