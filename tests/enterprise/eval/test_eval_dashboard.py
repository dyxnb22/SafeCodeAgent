"""Eval dashboard renderer tests."""

from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.eval.dashboard import render_dashboard, write_dashboard


def test_render_dashboard_contains_suite_table():
    markdown = render_dashboard(
        [
            EvaluationResult(case_id="smoke.pass_through", suite="smoke", passed=True),
            EvaluationResult(case_id="retrieval.policy.sql_injection", suite="retrieval", passed=True),
        ]
    )
    assert "## Suite: retrieval" in markdown
    assert "## Suite: smoke" in markdown
    assert "smoke.pass_through" in markdown


def test_write_dashboard_to_sac(tmp_path):
    path = write_dashboard(tmp_path / ".sac", "# dashboard\n")
    assert path.name == "latest.md"
    assert path.is_file()
