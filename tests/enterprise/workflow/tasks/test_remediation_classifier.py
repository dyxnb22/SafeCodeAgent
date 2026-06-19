"""Remediation classifier and planner tests."""

import asyncio
from pathlib import Path

from safecode.enterprise.workflow.nodes.plan import run as plan_run
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.tasks.remediation import classify_finding, ingest_findings
from safecode.enterprise.workflow.types import TaskType

_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = "examples/enterprise/fixtures/remediation/sql_injection"


def test_classifier_maps_sql_injection_rule():
    finding = ingest_findings(_ROOT, _FIXTURE)[0]
    assert classify_finding(finding) == "sql_injection"


def test_plan_references_policy_citation():
    state = build_initial_state(
        task_type=TaskType.remediation,
        input_ref=_FIXTURE,
        actor_id="user:security",
        repo_root=_ROOT,
        run_id="run-remclass01",
    )
    findings = ingest_findings(_ROOT, _FIXTURE)
    state = state.model_copy(update={"findings": findings, "risk_tier": findings[0].severity})
    from safecode.enterprise.workflow.tasks import remediation

    citations = remediation.retrieve_citations(state, findings)
    state = state.model_copy(update={"citations": citations})
    patch = asyncio.run(plan_run(state))
    plan = patch.state_updates["plan"]
    assert plan.actions
    assert "policy" in plan.actions[0].title.lower() or "secure" in plan.actions[0].title.lower()
