"""Validation rerun tests for remediation."""

from safecode.enterprise.workflow.state import EnterpriseRunState, Location, RBACSubject, RepoContext, RunRequest, SecurityFinding
from safecode.enterprise.workflow.tasks.remediation import run_post_apply_validation, run_pre_apply_validation
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus


def _state(repo_root: str = "/tmp/repo", **extra) -> EnterpriseRunState:
    return EnterpriseRunState(
        run_id="run-valid001",
        task_type=TaskType.remediation,
        status=WorkflowStatus.running,
        actor_id="user:test",
        subject=RBACSubject(actor_id="user:test"),
        policy_snapshot_id="snapshot-test",
        request=RunRequest(
            task_type=TaskType.remediation,
            input_kind="finding_fixture",
            input_ref="fixture.json",
            actor_id="user:test",
            extra=extra,
        ),
        repo=RepoContext(repo_root=repo_root),
        created_at="2026-06-19T00:00:00+00:00",
        updated_at="2026-06-19T00:00:00+00:00",
    )


def test_pre_apply_validation_reports_tests_and_scanner():
    result = run_pre_apply_validation(_state())
    assert result.passed is True
    assert result.details["tests"] == "passed"
    assert result.details["scanner"] == "proposed"


def test_post_apply_validation_reports_scanner_diff(tmp_path):
    (tmp_path / "app.py").write_text(
        'def fetch(user_id):\n    query = "SELECT * FROM users WHERE id=?"\n'
        "    return db.execute(query, (user_id,))\n",
        encoding="utf-8",
    )
    finding = SecurityFinding(
        finding_id="f1",
        source="semgrep",
        rule_id="sql-injection",
        severity=RiskTier.high,
        title="sql",
        description="sql",
        location=Location(path="app.py", start_line=1, end_line=2, snippet_hash="x"),
    )
    result = run_post_apply_validation(_state(repo_root=str(tmp_path)), finding=finding)
    assert result.passed is True
    assert "scanner_diff" in result.details


def test_post_apply_validation_marks_regression():
    result = run_post_apply_validation(_state(post_validation_failed="1"), finding=None, regression=True)
    assert result.passed is False
    assert result.details["scanner_diff"] == "new_findings=1"
