"""PR review report renderer tests."""

from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.render_pr_report import render_pr_report
from safecode.enterprise.workflow.state import (
    EnterpriseRunState,
    Location,
    RBACSubject,
    RepoContext,
    RunRequest,
    SecurityFinding,
)
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus


def _state(**updates) -> EnterpriseRunState:
    base = EnterpriseRunState(
        run_id="run-report001",
        task_type=TaskType.pr_review,
        status=WorkflowStatus.running,
        actor_id="user:test",
        subject=RBACSubject(actor_id="user:test"),
        policy_snapshot_id="snapshot-test",
        request=RunRequest(
            task_type=TaskType.pr_review,
            input_kind="pr_fixture",
            input_ref="fixture.json",
            actor_id="user:test",
        ),
        repo=RepoContext(repo_root="/tmp/repo"),
        created_at="2026-06-19T00:00:00+00:00",
        updated_at="2026-06-19T00:00:00+00:00",
    )
    return base.model_copy(update=updates)


def test_render_pr_report_contains_required_sections():
    markdown = render_pr_report(
        _state(
            risk_tier=RiskTier.high,
            findings=[
                SecurityFinding(
                    finding_id="finding-1",
                    source="agent_analysis",
                    rule_id="sql-injection",
                    severity=RiskTier.high,
                    title="SQL injection",
                    description="Unsafe query construction.",
                    cwe="CWE-89",
                    location=Location(path="app/db.py", start_line=5, end_line=8, snippet_hash="abc"),
                )
            ],
            citations=[
                Citation(
                    citation_id="cit-policy",
                    source_id="policy-secure-sql-001",
                    source_type=SourceType.security_policy,
                    path="examples/enterprise/policies/secure-sql.md",
                    start_line=1,
                    end_line=5,
                    score=0.9,
                    selection_reason="policy",
                    permission_verdict="allowed",
                    freshness="current",
                    hash="hash1",
                ),
                Citation(
                    citation_id="cit-code",
                    source_id="code-app",
                    source_type=SourceType.code,
                    path="examples/enterprise/sample_app/app.py",
                    start_line=1,
                    end_line=5,
                    score=0.8,
                    selection_reason="code",
                    permission_verdict="allowed",
                    freshness="current",
                    hash="hash2",
                ),
            ],
        )
    )
    for section in (
        "## Summary",
        "## Risk Findings",
        "## Cited Policies",
        "## Cited Code",
        "## Suggested Patch",
        "## Trace References",
    ):
        assert section in markdown
    assert "sql-injection" in markdown
    assert "examples/enterprise/policies/secure-sql.md" in markdown
