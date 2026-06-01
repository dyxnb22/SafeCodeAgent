"""Tests for v2.5.3 Quality Dashboard Report (src/safecode/report/dashboard.py)."""

from __future__ import annotations

import pytest

from safecode.eval.failures import ClassifiedFailure, FailureCategory
from safecode.eval.runner import ReplayResult, ValidationCommandResult
from safecode.report.dashboard import DashboardRenderer, ReportSummary, build_summary


# ── Helpers ──────────────────────────────────────────────────────────────────


def _passing_result(name: str = "fixture-pass") -> ReplayResult:
    return ReplayResult(
        fixture_name=name,
        passed=True,
        failure_reasons=[],
        validation_details=[],
        observed_changed_files=[],
        workspace_diff="",
        network_intent="denied",
        forbidden_commands_violated=[],
        forbidden_file_writes_violated=[],
        audit_events_status="ok",
        workspace_path=None,
        error=None,
        classified_failures=[],
    )


def _failing_result(
    name: str = "fixture-fail",
    reasons: list[str] | None = None,
    classified: list[ClassifiedFailure] | None = None,
    network_intent: str = "denied",
    audit_events_status: str = "ok",
    forbidden_commands: list[str] | None = None,
    forbidden_writes: list[str] | None = None,
    error: str | None = None,
) -> ReplayResult:
    return ReplayResult(
        fixture_name=name,
        passed=False,
        failure_reasons=reasons or ["Something went wrong."],
        validation_details=[],
        observed_changed_files=[],
        workspace_diff="",
        network_intent=network_intent,
        forbidden_commands_violated=forbidden_commands or [],
        forbidden_file_writes_violated=forbidden_writes or [],
        audit_events_status=audit_events_status,
        workspace_path=None,
        error=error,
        classified_failures=classified or [],
    )


def _classified(
    category: FailureCategory, reason: str, detail: str | None = None
) -> ClassifiedFailure:
    return ClassifiedFailure(category=category, reason=reason, detail=detail)


# ── TestBuildSummary ──────────────────────────────────────────────────────────


class TestBuildSummaryEmpty:
    def test_empty_returns_zero_counts(self) -> None:
        summary = build_summary([])
        assert summary.total == 0
        assert summary.passed == 0
        assert summary.failed == 0

    def test_empty_pass_rate_is_one(self) -> None:
        summary = build_summary([])
        assert summary.pass_rate == 1.0

    def test_empty_category_counts_empty(self) -> None:
        summary = build_summary([])
        assert summary.category_counts == {}

    def test_returns_report_summary_type(self) -> None:
        summary = build_summary([])
        assert isinstance(summary, ReportSummary)


class TestBuildSummaryAllPassing:
    def setup_method(self) -> None:
        self.results = [_passing_result(f"fix-{i}") for i in range(3)]
        self.summary = build_summary(self.results)

    def test_total(self) -> None:
        assert self.summary.total == 3

    def test_passed(self) -> None:
        assert self.summary.passed == 3

    def test_failed(self) -> None:
        assert self.summary.failed == 0

    def test_pass_rate_is_one(self) -> None:
        assert self.summary.pass_rate == 1.0

    def test_no_category_counts(self) -> None:
        assert self.summary.category_counts == {}


class TestBuildSummaryAllFailing:
    def setup_method(self) -> None:
        cf1 = _classified(FailureCategory.validation, "Expected output not found")
        cf2 = _classified(FailureCategory.setup, "Setup command failed")
        self.results = [
            _failing_result("a", classified=[cf1]),
            _failing_result("b", classified=[cf2]),
        ]
        self.summary = build_summary(self.results)

    def test_total(self) -> None:
        assert self.summary.total == 2

    def test_passed(self) -> None:
        assert self.summary.passed == 0

    def test_failed(self) -> None:
        assert self.summary.failed == 2

    def test_pass_rate_is_zero(self) -> None:
        assert self.summary.pass_rate == 0.0

    def test_category_counts_validation(self) -> None:
        assert self.summary.category_counts["validation"] == 1

    def test_category_counts_setup(self) -> None:
        assert self.summary.category_counts["setup"] == 1


class TestBuildSummaryMixed:
    def setup_method(self) -> None:
        cf_val = _classified(FailureCategory.validation, "r1")
        cf_cmd = _classified(FailureCategory.command_blocked, "r2", detail="rm")
        cf_cmd2 = _classified(FailureCategory.command_blocked, "r3", detail="dd")
        self.results = [
            _passing_result("pass-1"),
            _failing_result("fail-1", classified=[cf_val, cf_cmd]),
            _failing_result("fail-2", classified=[cf_cmd2]),
        ]
        self.summary = build_summary(self.results)

    def test_total(self) -> None:
        assert self.summary.total == 3

    def test_passed(self) -> None:
        assert self.summary.passed == 1

    def test_failed(self) -> None:
        assert self.summary.failed == 2

    def test_pass_rate(self) -> None:
        assert abs(self.summary.pass_rate - 1 / 3) < 1e-9

    def test_command_blocked_count(self) -> None:
        assert self.summary.category_counts["command_blocked"] == 2

    def test_validation_count(self) -> None:
        assert self.summary.category_counts["validation"] == 1


class TestBuildSummaryCategoryOrder:
    def test_categories_follow_enum_order(self) -> None:
        # Use multiple categories in non-alphabetical order
        cf_unknown = _classified(FailureCategory.unknown, "u")
        cf_validation = _classified(FailureCategory.validation, "v")
        cf_setup = _classified(FailureCategory.setup, "s")
        results = [_failing_result("x", classified=[cf_unknown, cf_validation, cf_setup])]
        summary = build_summary(results)
        keys = list(summary.category_counts.keys())
        # validation comes before setup comes before unknown in FailureCategory enum
        assert keys.index("validation") < keys.index("setup")
        assert keys.index("setup") < keys.index("unknown")

    def test_deterministic_across_calls(self) -> None:
        cf = _classified(FailureCategory.timeout, "t")
        results = [_failing_result("x", classified=[cf])]
        s1 = build_summary(results)
        s2 = build_summary(results)
        assert s1.category_counts == s2.category_counts


# ── TestMarkdownRendering ─────────────────────────────────────────────────────


class TestMarkdownEmpty:
    def setup_method(self) -> None:
        self.md = DashboardRenderer().render_markdown([], title="Test Report")

    def test_contains_title(self) -> None:
        assert "# Test Report" in self.md

    def test_contains_summary_heading(self) -> None:
        assert "## Summary" in self.md

    def test_total_zero(self) -> None:
        assert "**Total fixtures:** 0" in self.md

    def test_passed_zero(self) -> None:
        assert "**Passed:** 0" in self.md

    def test_failed_zero(self) -> None:
        assert "**Failed:** 0" in self.md

    def test_pass_rate_100(self) -> None:
        assert "100.0%" in self.md

    def test_no_category_table(self) -> None:
        assert "## Failure Categories" not in self.md

    def test_no_results_placeholder(self) -> None:
        assert "*No results.*" in self.md

    def test_no_failure_details(self) -> None:
        assert "## Failure Details" not in self.md


class TestMarkdownPassingOnly:
    def setup_method(self) -> None:
        results = [_passing_result("alpha"), _passing_result("beta")]
        self.md = DashboardRenderer().render_markdown(results, title="Pass Report")

    def test_title(self) -> None:
        assert "# Pass Report" in self.md

    def test_passed_count(self) -> None:
        assert "**Passed:** 2" in self.md

    def test_failed_count(self) -> None:
        assert "**Failed:** 0" in self.md

    def test_pass_rate_100(self) -> None:
        assert "100.0%" in self.md

    def test_fixture_names_present(self) -> None:
        assert "alpha" in self.md
        assert "beta" in self.md

    def test_status_pass(self) -> None:
        assert "PASS" in self.md

    def test_no_failure_details(self) -> None:
        assert "## Failure Details" not in self.md

    def test_no_category_table(self) -> None:
        assert "## Failure Categories" not in self.md


class TestMarkdownFailedReports:
    def setup_method(self) -> None:
        cf = _classified(
            FailureCategory.validation, "Expected output to contain 'ok'", detail=None
        )
        self.result = _failing_result(
            "fail-fixture",
            reasons=["Expected output to contain 'ok' but it was not found."],
            classified=[cf],
            network_intent="allowed",
            audit_events_status="pending_no_session_replay_source",
        )
        self.md = DashboardRenderer().render_markdown([self.result])

    def test_failure_categories_heading(self) -> None:
        assert "## Failure Categories" in self.md

    def test_validation_category_in_table(self) -> None:
        assert "validation" in self.md

    def test_fixture_name_in_results_table(self) -> None:
        assert "fail-fixture" in self.md

    def test_fail_status(self) -> None:
        assert "FAIL" in self.md

    def test_network_intent(self) -> None:
        assert "allowed" in self.md

    def test_audit_events_status(self) -> None:
        assert "pending_no_session_replay_source" in self.md

    def test_failure_details_heading(self) -> None:
        assert "## Failure Details" in self.md

    def test_failure_reason_present(self) -> None:
        assert "Expected output to contain" in self.md

    def test_classified_failures_table(self) -> None:
        assert "Classified failures" in self.md


class TestMarkdownForbiddenViolations:
    def setup_method(self) -> None:
        cf_cmd = _classified(FailureCategory.command_blocked, "Forbidden command: rm", detail="rm")
        cf_fw = _classified(FailureCategory.forbidden_file_write, "Forbidden write: .env", detail=".env")
        self.result = _failing_result(
            "security-fixture",
            forbidden_commands=["rm"],
            forbidden_writes=[".env"],
            classified=[cf_cmd, cf_fw],
        )
        self.md = DashboardRenderer().render_markdown([self.result])

    def test_forbidden_commands_section(self) -> None:
        assert "Forbidden commands violated" in self.md

    def test_forbidden_command_name(self) -> None:
        assert "`rm`" in self.md

    def test_forbidden_writes_section(self) -> None:
        assert "Forbidden file writes violated" in self.md

    def test_forbidden_write_name(self) -> None:
        assert "`.env`" in self.md

    def test_command_blocked_category(self) -> None:
        assert "command_blocked" in self.md

    def test_forbidden_file_write_category(self) -> None:
        assert "forbidden_file_write" in self.md


class TestMarkdownErrorResult:
    def setup_method(self) -> None:
        cf = _classified(FailureCategory.setup, "Workspace materialisation failed: disk full")
        self.result = _failing_result(
            "error-fixture",
            error="Workspace materialisation failed: disk full",
            classified=[cf],
        )
        self.md = DashboardRenderer().render_markdown([self.result])

    def test_error_shown_in_details(self) -> None:
        assert "Workspace materialisation failed" in self.md

    def test_setup_category_present(self) -> None:
        assert "setup" in self.md


class TestMarkdownDeterminism:
    def test_same_results_same_output(self) -> None:
        results = [_passing_result("a"), _failing_result("b")]
        r1 = DashboardRenderer().render_markdown(results)
        r2 = DashboardRenderer().render_markdown(results)
        assert r1 == r2

    def test_default_title(self) -> None:
        md = DashboardRenderer().render_markdown([])
        assert "# Eval Report" in md

    def test_custom_title(self) -> None:
        md = DashboardRenderer().render_markdown([], title="My Custom Title")
        assert "# My Custom Title" in md


class TestMarkdownMultipleFailures:
    def test_pass_rate_calculation(self) -> None:
        results = [_passing_result()] + [_failing_result(f"f{i}") for i in range(3)]
        md = DashboardRenderer().render_markdown(results)
        assert "25.0%" in md

    def test_all_fixture_names_present(self) -> None:
        names = ["alpha", "beta", "gamma"]
        results = [_failing_result(n) for n in names]
        md = DashboardRenderer().render_markdown(results)
        for name in names:
            assert name in md

    def test_multiple_category_counts(self) -> None:
        cf1 = _classified(FailureCategory.validation, "v")
        cf2 = _classified(FailureCategory.timeout, "t")
        cf3 = _classified(FailureCategory.validation, "v2")
        results = [
            _failing_result("a", classified=[cf1, cf2]),
            _failing_result("b", classified=[cf3]),
        ]
        md = DashboardRenderer().render_markdown(results)
        assert "validation" in md
        assert "timeout" in md


class TestMarkdownPipeEscaping:
    def test_pipe_in_reason_escaped(self) -> None:
        result = _failing_result("pipe-test", reasons=["Error: foo | bar caused issue"])
        md = DashboardRenderer().render_markdown([result])
        assert "foo \\| bar" in md

    def test_pipe_in_fixture_metadata_escaped(self) -> None:
        result = _failing_result(
            "fixture | name",
            network_intent="allowed | denied",
            audit_events_status="ok | pending",
        )
        md = DashboardRenderer().render_markdown([result])
        assert "fixture \\| name" in md
        assert "allowed \\| denied" in md
        assert "ok \\| pending" in md

    def test_pipe_in_classified_failure_fields_escaped(self) -> None:
        cf = _classified(
            FailureCategory.validation,
            "reason | with pipe",
            detail="detail | with pipe",
        )
        result = _failing_result("classified-pipe", classified=[cf])
        md = DashboardRenderer().render_markdown([result])
        assert "reason \\| with pipe" in md
        assert "detail \\| with pipe" in md


# ── TestHtmlRendering ─────────────────────────────────────────────────────────


class TestHtmlEmpty:
    def setup_method(self) -> None:
        self.html = DashboardRenderer().render_html([], title="Test HTML")

    def test_doctype(self) -> None:
        assert "<!DOCTYPE html>" in self.html

    def test_title_tag(self) -> None:
        assert "<title>Test HTML</title>" in self.html

    def test_h1_title(self) -> None:
        assert "<h1>Test HTML</h1>" in self.html

    def test_summary_heading(self) -> None:
        assert "<h2>Summary</h2>" in self.html

    def test_total_zero(self) -> None:
        assert "Total fixtures:" in self.html
        assert "0</li>" in self.html

    def test_pass_rate_100(self) -> None:
        assert "100.0%" in self.html

    def test_no_results_placeholder(self) -> None:
        assert "<em>No results.</em>" in self.html

    def test_no_failure_details_heading(self) -> None:
        assert "Failure Details" not in self.html

    def test_closes_html_tag(self) -> None:
        assert "</html>" in self.html


class TestHtmlPassingOnly:
    def setup_method(self) -> None:
        results = [_passing_result("alpha"), _passing_result("beta")]
        self.html = DashboardRenderer().render_html(results, title="Pass HTML")

    def test_title(self) -> None:
        assert "<title>Pass HTML</title>" in self.html

    def test_pass_status_class(self) -> None:
        assert 'class="pass"' in self.html

    def test_pass_text(self) -> None:
        assert ">PASS<" in self.html

    def test_fixture_names(self) -> None:
        assert "alpha" in self.html
        assert "beta" in self.html

    def test_no_failure_details(self) -> None:
        assert "Failure Details" not in self.html

    def test_no_category_table_when_no_failures(self) -> None:
        assert "Failure Categories" not in self.html


class TestHtmlFailedReport:
    def setup_method(self) -> None:
        cf = _classified(FailureCategory.validation, "Expected output not found")
        self.result = _failing_result(
            "html-fail",
            reasons=["Expected output to contain 'hello'."],
            classified=[cf],
            network_intent="allowed",
            audit_events_status="pending_no_session_replay_source",
        )
        self.html = DashboardRenderer().render_html([self.result])

    def test_fail_status_class(self) -> None:
        assert 'class="fail"' in self.html

    def test_fail_text(self) -> None:
        assert ">FAIL<" in self.html

    def test_fixture_name(self) -> None:
        assert "html-fail" in self.html

    def test_network_intent(self) -> None:
        assert "allowed" in self.html

    def test_audit_status(self) -> None:
        assert "pending_no_session_replay_source" in self.html

    def test_failure_categories_section(self) -> None:
        assert "Failure Categories" in self.html

    def test_validation_category(self) -> None:
        assert "validation" in self.html

    def test_failure_details_section(self) -> None:
        assert "Failure Details" in self.html

    def test_failure_reason(self) -> None:
        assert "Expected output to contain" in self.html


class TestHtmlEscaping:
    def test_html_special_chars_in_title_escaped(self) -> None:
        html = DashboardRenderer().render_html([], title="<Script>Alert</Script>")
        assert "<Script>" not in html
        assert "&lt;Script&gt;" in html

    def test_html_in_fixture_name_escaped(self) -> None:
        result = _failing_result("<b>bold-fixture</b>")
        html = DashboardRenderer().render_html([result])
        assert "<b>bold-fixture</b>" not in html
        assert "&lt;b&gt;" in html

    def test_html_in_failure_reason_escaped(self) -> None:
        result = _failing_result("x", reasons=["Error: <script>xss</script>"])
        html = DashboardRenderer().render_html([result])
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_ampersand_in_reason_escaped(self) -> None:
        result = _failing_result("x", reasons=["a & b"])
        html = DashboardRenderer().render_html([result])
        assert "a &amp; b" in html


class TestHtmlForbiddenViolations:
    def setup_method(self) -> None:
        cf_cmd = _classified(FailureCategory.command_blocked, "Forbidden command: rm", detail="rm")
        cf_fw = _classified(FailureCategory.forbidden_file_write, "Forbidden write: .env", detail=".env")
        result = _failing_result(
            "sec",
            forbidden_commands=["rm"],
            forbidden_writes=[".env"],
            classified=[cf_cmd, cf_fw],
        )
        self.html = DashboardRenderer().render_html([result])

    def test_forbidden_commands_section(self) -> None:
        assert "Forbidden commands violated" in self.html

    def test_forbidden_command_code(self) -> None:
        assert "<code>rm</code>" in self.html

    def test_forbidden_writes_section(self) -> None:
        assert "Forbidden file writes violated" in self.html

    def test_forbidden_write_code(self) -> None:
        assert "<code>.env</code>" in self.html

    def test_classified_table_rendered(self) -> None:
        assert "Classified failures" in self.html
        assert "command_blocked" in self.html
        assert "forbidden_file_write" in self.html


class TestHtmlDeterminism:
    def test_same_results_same_output(self) -> None:
        results = [_passing_result("a"), _failing_result("b")]
        h1 = DashboardRenderer().render_html(results)
        h2 = DashboardRenderer().render_html(results)
        assert h1 == h2

    def test_default_title(self) -> None:
        html = DashboardRenderer().render_html([])
        assert "<title>Eval Report</title>" in html

    def test_custom_title(self) -> None:
        html = DashboardRenderer().render_html([], title="Custom")
        assert "<title>Custom</title>" in html
        assert "<h1>Custom</h1>" in html


# ── TestFailureCategoryAggregation ────────────────────────────────────────────


class TestFailureCategoryAggregation:
    def test_multiple_classified_in_one_result(self) -> None:
        cfs = [
            _classified(FailureCategory.validation, "v1"),
            _classified(FailureCategory.validation, "v2"),
            _classified(FailureCategory.timeout, "t1"),
        ]
        result = _failing_result("x", classified=cfs)
        summary = build_summary([result])
        assert summary.category_counts["validation"] == 2
        assert summary.category_counts["timeout"] == 1

    def test_aggregated_across_results(self) -> None:
        cfs_a = [_classified(FailureCategory.setup, "s")]
        cfs_b = [_classified(FailureCategory.setup, "s2"), _classified(FailureCategory.unknown, "u")]
        results = [
            _failing_result("a", classified=cfs_a),
            _failing_result("b", classified=cfs_b),
        ]
        summary = build_summary(results)
        assert summary.category_counts["setup"] == 2
        assert summary.category_counts["unknown"] == 1

    def test_passing_results_do_not_contribute_categories(self) -> None:
        results = [_passing_result(), _failing_result("x")]
        summary = build_summary(results)
        # Only the failing one (with empty classified_failures) contributes
        assert summary.category_counts == {}

    def test_all_failure_categories_recognized(self) -> None:
        cfs = [_classified(cat, f"reason-{cat}") for cat in FailureCategory]
        result = _failing_result("all-cats", classified=cfs)
        summary = build_summary([result])
        for cat in FailureCategory:
            assert cat.value in summary.category_counts

    def test_category_counts_not_in_markdown_when_empty(self) -> None:
        results = [_failing_result("x", classified=[])]
        md = DashboardRenderer().render_markdown(results)
        assert "## Failure Categories" not in md

    def test_category_counts_in_html_when_present(self) -> None:
        cf = _classified(FailureCategory.patch_parse, "parse error")
        results = [_failing_result("x", classified=[cf])]
        html = DashboardRenderer().render_html(results)
        assert "patch_parse" in html
        assert "Failure Categories" in html


# ── TestReplayResultBackwardCompat ────────────────────────────────────────────


class TestReplayResultBackwardCompat:
    def test_replay_result_without_classified_failures(self) -> None:
        # Construct without classified_failures — default should be empty list
        result = ReplayResult(
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
        assert result.classified_failures == []

    def test_build_summary_with_result_no_classified(self) -> None:
        result = ReplayResult(
            fixture_name="compat2",
            passed=False,
            failure_reasons=["something"],
            validation_details=[],
            observed_changed_files=[],
            workspace_diff="",
            network_intent="denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="ok",
        )
        # Should not raise; classified_failures defaults to []
        summary = build_summary([result])
        assert summary.total == 1
        assert summary.category_counts == {}

    def test_renderer_accepts_result_no_classified(self) -> None:
        result = ReplayResult(
            fixture_name="compat3",
            passed=False,
            failure_reasons=["oops"],
            validation_details=[],
            observed_changed_files=[],
            workspace_diff="",
            network_intent="denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="ok",
        )
        md = DashboardRenderer().render_markdown([result])
        assert "compat3" in md
        html = DashboardRenderer().render_html([result])
        assert "compat3" in html


# ── TestValidationDetails integration ────────────────────────────────────────


class TestValidationDetailsInResult:
    def test_passing_result_with_validation_details(self) -> None:
        vd = ValidationCommandResult(
            command="pytest -q", exit_code=0, stdout="5 passed", stderr="", passed=True
        )
        result = ReplayResult(
            fixture_name="with-vd",
            passed=True,
            failure_reasons=[],
            validation_details=[vd],
            observed_changed_files=["src/foo.py"],
            workspace_diff="--- a/src/foo.py\n+++ b/src/foo.py\n",
            network_intent="denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="ok",
            classified_failures=[],
        )
        summary = build_summary([result])
        assert summary.passed == 1
        md = DashboardRenderer().render_markdown([result])
        assert "PASS" in md
