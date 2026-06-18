"""Tests for Semgrep loader (v1.1.1-T6)."""

import json
from pathlib import Path

from safecode.enterprise.rag.loaders.loader_semgrep import load_semgrep_source
from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType

_SOURCE = KnowledgeSource(
    source_id="scanner-semgrep",
    source_type=SourceType.scanner_finding,
    name="Semgrep",
    path_or_uri="semgrep.json",
    owner="appsec",
    permission_scope=["org"],
    refresh_cadence="on_demand",
    parser="semgrep",
)


def test_accepts_semgrep_results_shape(tmp_path: Path):
    payload = {
        "results": [
            {
                "check_id": "python.lang.security.audit.sql-injection",
                "path": "app/db.py",
                "start": {"line": 4, "col": 1},
                "end": {"line": 6, "col": 1},
                "extra": {"message": "Possible SQL injection", "severity": "ERROR"},
            }
        ]
    }
    (tmp_path / "semgrep.json").write_text(json.dumps(payload), encoding="utf-8")
    result = load_semgrep_source(_SOURCE, tmp_path)
    assert len(result.records) == 1
    assert result.records[0].metadata["check_id"].endswith("sql-injection")


def test_record_id_is_stable(tmp_path: Path):
    payload = {
        "results": [
            {
                "check_id": "rule-a",
                "path": "app/db.py",
                "start": {"line": 1},
                "extra": {"message": "Finding"},
            }
        ]
    }
    (tmp_path / "semgrep.json").write_text(json.dumps(payload), encoding="utf-8")
    first = load_semgrep_source(_SOURCE, tmp_path).records[0].record_id
    second = load_semgrep_source(_SOURCE, tmp_path).records[0].record_id
    assert first == second
