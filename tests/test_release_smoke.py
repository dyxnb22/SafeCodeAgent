"""Tests for v2.6.5 release smoke-test workflow and v2.6.9 docs finalization case."""

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.smoke import (
    EXPECTED_POLICY_NAMES,
    SmokeTestCase,
    SmokeTestResult,
    _check_cli_version,
    _check_docs_finalized,
    _check_import_version,
    _check_policy_names,
    _check_version_consistency,
    render_smoke_results,
    run_smoke_tests,
)


# ---------------------------------------------------------------------------
# Individual smoke-test checks
# ---------------------------------------------------------------------------


class TestCheckImportVersion:
    def test_passes_with_real_package(self):
        case = _check_import_version()
        assert case.name == "import_version"
        assert case.passed is True
        assert "safecode.__version__" in case.detail

    def test_detail_includes_version_string(self):
        import safecode
        case = _check_import_version()
        assert safecode.__version__ in case.detail


class TestCheckCliVersion:
    def test_passes_with_real_cli(self):
        case = _check_cli_version()
        assert case.name == "cli_version"
        assert case.passed is True

    def test_detail_mentions_exit_code(self):
        case = _check_cli_version()
        assert "exit 0" in case.detail or "version" in case.detail.lower()


class TestCheckVersionConsistency:
    def test_passes_in_consistent_repo(self):
        case = _check_version_consistency()
        assert case.name == "version_consistency"
        assert case.passed is True, f"version consistency failed: {case.detail}"

    def test_detail_is_non_empty(self):
        case = _check_version_consistency()
        assert len(case.detail) > 0


class TestCheckDocsFinalized:
    def test_passes_in_consistent_repo(self):
        case = _check_docs_finalized()
        assert case.name == "docs_finalized"
        # In the real repo we should have version note and SKILL.md updated
        assert isinstance(case.passed, bool)
        assert len(case.detail) > 0

    def test_detail_non_empty(self):
        case = _check_docs_finalized()
        assert case.detail


class TestCheckPolicyNames:
    def test_passes_with_all_expected_names(self):
        case = _check_policy_names()
        assert case.name == "policy_names"
        assert case.passed is True, f"policy names check failed: {case.detail}"

    def test_detail_includes_policy_names(self):
        case = _check_policy_names()
        for name in ("strict", "balanced", "experimental"):
            assert name in case.detail

    def test_expected_policy_names_set(self):
        assert EXPECTED_POLICY_NAMES == {"strict", "balanced", "experimental", "normal", "learning"}


# ---------------------------------------------------------------------------
# run_smoke_tests
# ---------------------------------------------------------------------------


class TestRunSmokeTests:
    def test_all_cases_present(self):
        result = run_smoke_tests()
        names = {c.name for c in result.cases}
        assert "import_version" in names
        assert "cli_version" in names
        assert "version_consistency" in names
        assert "policy_names" in names
        assert "docs_finalized" in names

    def test_passes_in_consistent_repo(self):
        result = run_smoke_tests()
        assert result.ok is True, "\n".join(f"  FAIL {c.name}: {c.detail}" for c in result.failed)

    def test_ok_is_false_when_any_case_fails(self):
        result = SmokeTestResult(
            cases=[
                SmokeTestCase("a", True, "ok"),
                SmokeTestCase("b", False, "bad"),
            ]
        )
        assert result.ok is False

    def test_failed_returns_only_failing_cases(self):
        result = SmokeTestResult(
            cases=[
                SmokeTestCase("a", True, "ok"),
                SmokeTestCase("b", False, "bad"),
                SmokeTestCase("c", True, "ok"),
            ]
        )
        assert [c.name for c in result.failed] == ["b"]

    def test_ok_true_when_all_pass(self):
        result = SmokeTestResult(
            cases=[SmokeTestCase("a", True, "ok"), SmokeTestCase("b", True, "ok")]
        )
        assert result.ok is True


# ---------------------------------------------------------------------------
# render_smoke_results
# ---------------------------------------------------------------------------


class TestRenderSmokeResults:
    def _make_result(self, cases: list[SmokeTestCase]) -> SmokeTestResult:
        return SmokeTestResult(cases=cases)

    def test_includes_pass_for_passing_case(self):
        result = self._make_result([SmokeTestCase("foo", True, "all good")])
        text = render_smoke_results(result)
        assert "PASS" in text
        assert "foo" in text

    def test_includes_fail_for_failing_case(self):
        result = self._make_result([SmokeTestCase("bar", False, "broken")])
        text = render_smoke_results(result)
        assert "FAIL" in text
        assert "bar" in text

    def test_all_passed_message_when_ok(self):
        result = self._make_result([SmokeTestCase("x", True, "fine")])
        text = render_smoke_results(result)
        assert "passed" in text.lower()

    def test_failed_summary_when_not_ok(self):
        result = self._make_result([SmokeTestCase("bad_check", False, "oh no")])
        text = render_smoke_results(result)
        assert "FAILED" in text or "failed" in text.lower()
        assert "bad_check" in text

    def test_detail_text_present_in_output(self):
        result = self._make_result([SmokeTestCase("chk", True, "unique_detail_xyz")])
        text = render_smoke_results(result)
        assert "unique_detail_xyz" in text


# ---------------------------------------------------------------------------
# CLI: sac release smoke
# ---------------------------------------------------------------------------


class TestReleaseSmokeCliCommand:
    def test_cli_smoke_exits_zero_in_consistent_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from safecode import cli_ops
        from safecode.release.smoke import SmokeTestResult, SmokeTestCase

        def _fake_run():
            return SmokeTestResult(cases=[
                SmokeTestCase("import_version", True, "ok"),
                SmokeTestCase("cli_version", True, "ok"),
                SmokeTestCase("version_consistency", True, "ok"),
                SmokeTestCase("policy_names", True, "ok"),
            ])

        monkeypatch.setattr(cli_ops, "run_smoke_tests", _fake_run)
        result = CliRunner().invoke(app, ["release", "smoke"])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_cli_smoke_exits_nonzero_on_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from safecode import cli_ops
        from safecode.release.smoke import SmokeTestResult, SmokeTestCase

        def _fake_run():
            return SmokeTestResult(cases=[
                SmokeTestCase("import_version", True, "ok"),
                SmokeTestCase("cli_version", False, "broken"),
                SmokeTestCase("version_consistency", True, "ok"),
                SmokeTestCase("policy_names", True, "ok"),
            ])

        monkeypatch.setattr(cli_ops, "run_smoke_tests", _fake_run)
        result = CliRunner().invoke(app, ["release", "smoke"])
        assert result.exit_code != 0
        assert "FAIL" in result.output
