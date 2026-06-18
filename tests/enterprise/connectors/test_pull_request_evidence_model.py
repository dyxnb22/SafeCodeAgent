"""PullRequestEvidence model tests (v1.3.2-T1)."""

import json

from safecode.enterprise.connectors.models import DiffHunk, PullRequestEvidence, PullRequestFile


def test_pull_request_evidence_json_round_trip():
    evidence = PullRequestEvidence(
        evidence_id="pre-abc123",
        title="Fix SQL injection",
        body="Parameterize queries.",
        author="dev@example.com",
        base_ref="main",
        head_ref="feature/sql-fix",
        labels=["security"],
        reviewers=["reviewer@example.com"],
        files=[PullRequestFile(path="app/db.py", status="modified")],
        hunks=[
            DiffHunk(
                hunk_id="hunk-001",
                file_path="app/db.py",
                start_line=10,
                end_line=12,
                patch="@@ -10,3 +10,3 @@",
            )
        ],
    )
    restored = PullRequestEvidence.model_validate(json.loads(evidence.model_dump_json()))
    assert restored == evidence
