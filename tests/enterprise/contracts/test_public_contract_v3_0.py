"""Enterprise GA v3.0 public contract snapshot tests (v3.0.1-T1)."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.enterprise.contracts.v2_1 import assert_snapshot_safe
from safecode.enterprise.contracts.v3_0 import enterprise_ga_v3_0_contract

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "ga_v3_0.json"


def _load_snapshot() -> dict:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def test_ga_v3_0_snapshot_matches_live() -> None:
    expected = _load_snapshot()
    live = enterprise_ga_v3_0_contract()
    assert live == expected, (
        "v3.0 GA contract drift; update tests/enterprise/contracts/snapshots/ga_v3_0.json"
    )


def test_ga_v3_0_snapshot_file_exists() -> None:
    assert _SNAPSHOT.is_file()


def test_ga_v3_0_contract_status_is_supported() -> None:
    live = enterprise_ga_v3_0_contract()
    assert live["contract_status"] == "supported"
    assert live["openapi_x_contract_status"] == "supported"


def test_ga_v3_0_snapshot_scrubs_secrets_and_host_paths() -> None:
    assert_snapshot_safe(enterprise_ga_v3_0_contract())


def test_ga_v3_0_includes_v2_0_rc_contract_digests() -> None:
    live = enterprise_ga_v3_0_contract()
    assert "enterprise_cli" in live["v2_0_rc_contract_digests"]
    assert len(live["v2_0_rc_contracts"]) == len(live["v2_0_rc_contract_digests"])


def test_unreviewed_contract_breaking_change_fails_snapshot() -> None:
    live = enterprise_ga_v3_0_contract()
    tampered = dict(live)
    tampered["decision_refs"] = []
    expected = _load_snapshot()
    assert tampered != expected


def test_forbidden_token_in_snapshot_material_fails_scrub() -> None:
    live = enterprise_ga_v3_0_contract()
    tampered = dict(live)
    tampered["migration_from"] = "v2.0.0-rc ghp_secret"
    try:
        assert_snapshot_safe(tampered)
    except (AssertionError, ValueError):
        return
    raise AssertionError("expected forbidden token scrub failure")
