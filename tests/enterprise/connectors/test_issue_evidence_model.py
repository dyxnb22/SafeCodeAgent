"""IssueEvidence model tests (v1.3.3-T1)."""

import json

from safecode.enterprise.connectors.models import IssueEvidence


def test_issue_evidence_defaults_unknown_severity():
    evidence = IssueEvidence(
        evidence_id="issue-001",
        issue_id="SEC-101",
        title="SQL injection report",
        body="Untrusted input in login form.",
    )
    assert evidence.severity == "unknown"
    restored = IssueEvidence.model_validate(json.loads(evidence.model_dump_json()))
    assert restored == evidence
