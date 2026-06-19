"""Enterprise public contract snapshot tests (v2.0.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.enterprise.contracts.snapshot import all_contracts

_SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"


def _load(name: str) -> dict:
    return json.loads((_SNAPSHOTS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(all_contracts().keys()))
def test_contract_snapshot_matches_live(name: str):
    expected = _load(name)
    live = all_contracts()[name]
    assert live == expected, f"{name} contract drift; update tests/enterprise/contracts/snapshots/{name}.json"


def test_snapshot_files_exist():
    for name in all_contracts():
        assert (_SNAPSHOTS / f"{name}.json").is_file()
