"""Duplicate case id detection tests."""

from pathlib import Path

import pytest

from safecode.enterprise.eval.exceptions import DuplicateCaseIdError
from safecode.enterprise.eval.loader import discover_cases


def test_duplicate_case_id_raises(tmp_path: Path):
    cases_root = tmp_path / "cases" / "smoke"
    cases_root.mkdir(parents=True)
    payload = """case_id: smoke.dup
suite: smoke
goal: first
"""
    (cases_root / "a.yaml").write_text(payload, encoding="utf-8")
    (cases_root / "b.yaml").write_text(payload, encoding="utf-8")
    with pytest.raises(DuplicateCaseIdError):
        discover_cases(tmp_path / "cases", suite="smoke")
