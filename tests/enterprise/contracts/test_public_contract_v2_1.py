"""Team Server v2.1 public contract snapshot tests (v2.1.7-T1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.enterprise.contracts.v2_1 import assert_snapshot_safe, team_server_v2_1_contract

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "api_v2_1.json"


def _load_snapshot() -> dict:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def test_api_v2_1_snapshot_matches_live() -> None:
    expected = _load_snapshot()
    live = team_server_v2_1_contract()
    assert live == expected, (
        "v2.1 Team Server contract drift; update tests/enterprise/contracts/snapshots/api_v2_1.json"
    )


def test_api_v2_1_snapshot_file_exists() -> None:
    assert _SNAPSHOT.is_file()


def test_api_v2_1_snapshot_scrubs_secrets_and_host_paths() -> None:
    assert_snapshot_safe(team_server_v2_1_contract())


def test_api_v2_1_run_statuses_match_workflow_enum() -> None:
    live = team_server_v2_1_contract()
    assert live["run_statuses_match_openapi"] is True


def test_api_v2_1_includes_security_error_responses() -> None:
    live = team_server_v2_1_contract()
    assert "401" in live["security_response_status_codes"]
    assert "403" in live["security_response_status_codes"]


def test_unreviewed_security_response_removal_fails_snapshot() -> None:
    live = team_server_v2_1_contract()
    tampered = dict(live)
    tampered["security_response_status_codes"] = ["401"]
    expected = _load_snapshot()
    assert tampered != expected
