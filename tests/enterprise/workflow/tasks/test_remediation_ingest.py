"""Remediation finding ingestion tests."""

import asyncio
from pathlib import Path

import pytest

from safecode.enterprise.workflow.nodes.collect_context import run as collect_run
from safecode.enterprise.workflow.nodes.retrieve import run as retrieve_run
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.tasks.remediation import code_citations, ingest_findings, policy_citations
from safecode.enterprise.workflow.types import TaskType

_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = "examples/enterprise/fixtures/remediation/sql_injection"


def test_ingest_semgrep_fixture_returns_findings():
    findings = ingest_findings(_ROOT, _FIXTURE)
    assert len(findings) == 1
    assert findings[0].source == "semgrep"
    assert "sql" in findings[0].rule_id


def test_collect_context_rejects_path_traversal(tmp_path: Path):
    state = build_initial_state(
        task_type=TaskType.remediation,
        input_ref="../../../etc/passwd",
        actor_id="user:security",
        repo_root=tmp_path,
        run_id="run-traversal01",
    )
    with pytest.raises(ValueError, match="escapes repository root"):
        asyncio.run(collect_run(state))


def test_collect_context_attaches_findings_and_retrieve_adds_citations():
    state = build_initial_state(
        task_type=TaskType.remediation,
        input_ref=_FIXTURE,
        actor_id="user:security",
        repo_root=_ROOT,
        run_id="run-remedi001",
    )
    collect_patch = asyncio.run(collect_run(state))
    state = state.model_copy(update=collect_patch.state_updates)
    assert state.findings
    assert state.missing_evidence is False
    retrieve_patch = asyncio.run(retrieve_run(state))
    state = state.model_copy(update=retrieve_patch.state_updates)
    assert policy_citations(state.citations) or code_citations(state.citations)
