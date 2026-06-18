"""Tests for SARIF loader (v1.1.1-T5)."""

import json
from pathlib import Path

import pytest

from safecode.enterprise.rag.exceptions import UnsupportedSarifVersionError
from safecode.enterprise.rag.loaders.loader_sarif import load_sarif_source
from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType

_SOURCE = KnowledgeSource(
    source_id="scanner-sarif",
    source_type=SourceType.scanner_finding,
    name="SARIF",
    path_or_uri="findings.sarif",
    owner="appsec",
    permission_scope=["org"],
    refresh_cadence="on_demand",
    parser="sarif",
)


def _write_sarif(path: Path, version: str) -> None:
    payload = {
        "version": version,
        "runs": [
            {
                "results": [
                    {
                        "ruleId": "sql-injection",
                        "message": {"text": "Possible SQL injection"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "app/db.py"},
                                    "region": {"startLine": 10, "endLine": 12},
                                }
                            }
                        ],
                    }
                ]
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_emits_one_record_per_result(tmp_path: Path):
    _write_sarif(tmp_path / "findings.sarif", "2.1.0")
    result = load_sarif_source(_SOURCE, tmp_path)
    assert len(result.records) == 1
    assert result.records[0].path == "app/db.py"
    assert result.records[0].span.start_line == 10


def test_unsupported_version_raises(tmp_path: Path):
    _write_sarif(tmp_path / "findings.sarif", "2.0.0")
    with pytest.raises(UnsupportedSarifVersionError):
        load_sarif_source(_SOURCE, tmp_path)
