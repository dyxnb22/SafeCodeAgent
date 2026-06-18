"""GitHub PR connector redaction tests (v1.3.2-T2)."""

import json
import re
from pathlib import Path

from safecode.enterprise.connectors.github_pr import PullRequestConnectorSpec, fetch_pr

_TOKEN_RE = re.compile(r"gh[ps]_[A-Za-z0-9]{20,}")


def test_redaction_removes_tokens_and_authorization(tmp_path: Path):
    payload = {
        "title": "Secret leak",
        "body": "Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz123456",
        "author": "dev@example.com",
        "base_ref": "main",
        "head_ref": "feature/x",
        "files": [],
        "hunks": [],
    }
    fixture = tmp_path / "pr.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    evidence = fetch_pr(
        PullRequestConnectorSpec(mode="fixture", fixture_path=str(fixture.name), project_root=str(tmp_path))
    )
    blob = evidence.model_dump_json()
    assert "Authorization:" not in blob
    assert _TOKEN_RE.search(blob) is None
