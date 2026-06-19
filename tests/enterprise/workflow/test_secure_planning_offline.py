"""Secure planning workflow offline tests (v2.4.5)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.tasks.secure_planning import policy_citations
from safecode.enterprise.workflow.types import RiskTier, TaskType

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = "examples/enterprise/fixtures/ticket_password_reset/ticket.md"


def _cleanup_run(sac_root: Path, run_id: str) -> None:
    import shutil

    run_dir = sac_root / "enterprise" / "runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    approval_dir = sac_root / "enterprise" / "approvals" / run_id
    if approval_dir.exists():
        shutil.rmtree(approval_dir)


def test_secure_planning_ticket_produces_cited_plan_with_alternatives(tmp_path: Path):
    sac_root = _ROOT / ".sac"
    run_id = "run-secureplan01"
    _cleanup_run(sac_root, run_id)
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.secure_planning,
        input_ref=_FIXTURE,
        actor_id="user:security",
        repo_root=_ROOT,
        run_id=run_id,
    )
    assert state.request.input_kind == "ticket"
    final = asyncio.run(orchestrator.run(state))
    assert final.status.value == "succeeded"
    assert final.issue_evidence is not None
    assert final.plan is not None
    assert final.plan.citation_ids
    assert len(final.plan.alternatives) >= 2
    assert final.plan.revisit_trigger
    assert policy_citations(final.citations)
    assert final.report is not None
    assert final.report.kind == "plan_report"
    assert "## Alternatives" in final.report.markdown
    assert "## Revisit Trigger" in final.report.markdown
    assert "## Citation IDs" in final.report.markdown
    plan_path = _ROOT / ".sac" / "enterprise" / "runs" / final.run_id / "plan.md"
    assert plan_path.is_file()


def test_secure_planning_missing_ticket_sets_missing_evidence(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.secure_planning,
        input_ref="examples/enterprise/fixtures/does_not_exist/ticket.md",
        actor_id="user:security",
        repo_root=_ROOT,
        run_id="run-secureplan02",
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.missing_evidence is True
    assert final.issue_evidence is None


def test_secure_planning_validation_skipped(tmp_path: Path):
    sac_root = _ROOT / ".sac"
    run_id = "run-secureplan03"
    _cleanup_run(sac_root, run_id)
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.secure_planning,
        input_ref=_FIXTURE,
        actor_id="user:security",
        repo_root=_ROOT,
        run_id=run_id,
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.validation is not None
    assert final.validation.passed is True
    assert final.validation.details.get("skipped") == "secure_planning does not run scanners"


def test_secure_planning_detects_token_handling_risk():
    from safecode.enterprise.connectors.models import IssueEvidence
    from safecode.enterprise.workflow.tasks.secure_planning import analyze_ticket_security

    evidence = IssueEvidence(
        evidence_id="issue-test",
        issue_id="TICKET-42",
        title="Password reset token reuse",
        body="Users can reuse password reset tokens across sessions.",
        labels=["security"],
        severity="medium",
    )
    findings, tier = analyze_ticket_security(evidence, citations=[])
    assert any(item.rule_id == "token-handling" for item in findings)
    assert tier in {RiskTier.medium, RiskTier.high}
