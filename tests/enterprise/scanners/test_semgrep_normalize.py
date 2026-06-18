"""Semgrep normalization tests."""

import json
from pathlib import Path

import pytest

from safecode.enterprise.scanners.semgrep import (
    UnsupportedScannerVersionError,
    normalize_semgrep,
    normalize_semgrep_json,
)

_FIXTURE = Path(__file__).resolve().parents[3] / "examples/enterprise/scanner_findings/semgrep_baseline.json"


def test_semgrep_normalize_deterministic_finding_id():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    first = normalize_semgrep(payload)
    second = normalize_semgrep(payload)
    assert first[0].finding_id == second[0].finding_id
    assert first[0].finding_id.startswith("finding-")


def test_unsupported_schema_version():
    with pytest.raises(UnsupportedScannerVersionError):
        normalize_semgrep({"results": []}, schema_version=99)


def test_normalize_semgrep_json():
    findings = normalize_semgrep_json(_FIXTURE.read_text(encoding="utf-8"))
    assert findings[0].source == "semgrep"
