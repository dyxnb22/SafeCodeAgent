"""PR review happy-path workflow tests."""

import asyncio
from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import approvals_dir
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.tasks.pr_review import code_citations, policy_citations
from safecode.enterprise.workflow.types import RiskTier, TaskType

_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = "examples/enterprise/fixtures/pr_sql_injection"


def _cleanup_run(sac_root: Path, run_id: str) -> None:
    import shutil

    run_dir = sac_root / "enterprise" / "runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    approval_dir = approvals_dir(sac_root, run_id)
    if approval_dir.exists():
        shutil.rmtree(approval_dir)


def test_pr_review_sql_injection_fixture_produces_cited_high_risk_report(tmp_path: Path):
    sac_root = _ROOT / ".sac"
    run_id = "run-prhappy002"
    _cleanup_run(sac_root, run_id)
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=_FIXTURE,
        actor_id="user:security",
        repo_root=_ROOT,
        run_id=run_id,
    )
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))
    final = load_checkpoint(sac_root, run_id).state
    assert final.risk_tier == RiskTier.high
    assert final.findings
    assert any(item.rule_id == "sql-injection" for item in final.findings)
    assert policy_citations(final.citations)
    assert code_citations(final.citations)
    report_path = _ROOT / ".sac" / "enterprise" / "runs" / final.run_id / "report.md"
    assert report_path.is_file()
    markdown = report_path.read_text(encoding="utf-8")
    assert "## Risk Findings" in markdown
    assert "sql-injection" in markdown.lower()
    assert any(item.source_type == SourceType.security_policy for item in final.citations)
    assert any(item.source_type == SourceType.code for item in final.citations)
