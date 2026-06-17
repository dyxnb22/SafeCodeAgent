"""Tests for eval snapshot comparison helper."""

from __future__ import annotations

import json
from pathlib import Path
import importlib.util


def _load_eval_compare():
    path = Path(__file__).resolve().parents[1] / "scripts" / "eval_compare.py"
    spec = importlib.util.spec_from_file_location("eval_compare_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_snapshot_files_reports_regression_and_improvement(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({
        "results": [
            {"fixture_name": "a", "success": True},
            {"fixture_name": "b", "success": False},
        ]
    }), encoding="utf-8")
    after.write_text(json.dumps({
        "results": [
            {"fixture_name": "a", "success": False},
            {"fixture_name": "b", "success": True},
        ]
    }), encoding="utf-8")
    module = _load_eval_compare()

    text = module._compare_snapshot_files(before, after)

    assert "REGRESSION" in text
    assert "IMPROVED" in text
    assert "Pass rate" in text
