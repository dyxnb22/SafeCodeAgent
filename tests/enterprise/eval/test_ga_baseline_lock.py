"""GA eval baseline lock tests (v3.0.4-T1)."""

from __future__ import annotations

import json
from pathlib import Path

_BASELINES = Path(__file__).resolve().parent / "baselines"
_LOCK = _BASELINES / "ga_lock_v3_0.json"
_REQUIRED_KEYS = ("suite", "date", "commit", "cases")


def test_ga_baseline_lock_manifest_exists() -> None:
    assert _LOCK.is_file()


def test_all_checked_in_baselines_match_ga_lock() -> None:
    lock = json.loads(_LOCK.read_text(encoding="utf-8"))
    locked = lock.get("baselines", {})
    for path in sorted(_BASELINES.glob("*.json")):
        if path.name == "ga_lock_v3_0.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key in _REQUIRED_KEYS:
            assert key in payload, f"{path.name} missing {key}"
        assert path.name in locked, f"{path.name} missing from GA lock manifest"
        assert locked[path.name] == payload.get("commit"), f"{path.name} commit drift"


def test_ga_lock_lists_all_suite_baselines() -> None:
    lock = json.loads(_LOCK.read_text(encoding="utf-8"))
    baseline_files = {
        path.name
        for path in _BASELINES.glob("*.json")
        if path.name != "ga_lock_v3_0.json"
    }
    assert set(lock.get("baselines", {})) == baseline_files
