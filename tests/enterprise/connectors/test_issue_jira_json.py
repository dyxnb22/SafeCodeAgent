"""Issue Jira JSON connector tests."""

import json
from pathlib import Path

from safecode.enterprise.connectors.issue import IssueConnectorSpec, fetch_issue


def test_issue_jira_json_matches_markdown_shape(tmp_path: Path):
    markdown = tmp_path / "ticket.md"
    markdown.write_text("# SQL injection in login\n\nSeverity: high\nLabels: security, bug\n", encoding="utf-8")
    md_evidence = fetch_issue(
        IssueConnectorSpec(source_kind="markdown", source_path=markdown.name, project_root=str(tmp_path))
    )

    jira = tmp_path / "ticket.json"
    jira.write_text(
        json.dumps(
            {
                "key": "SEC-101",
                "fields": {
                    "summary": "SQL injection in login",
                    "description": "",
                    "labels": [{"name": "security"}, {"name": "bug"}],
                    "priority": {"name": "high"},
                },
            }
        ),
        encoding="utf-8",
    )
    jira_evidence = fetch_issue(
        IssueConnectorSpec(source_kind="jira_json", source_path=jira.name, project_root=str(tmp_path))
    )
    assert jira_evidence.title == md_evidence.title
    assert jira_evidence.severity == md_evidence.severity
    assert jira_evidence.labels == md_evidence.labels
