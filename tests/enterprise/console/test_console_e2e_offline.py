"""Operator Console end-to-end offline acceptance tests (v2.3.5-T1)."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.enterprise.contracts.v2_3 import CONSOLE_SOURCE_FILES, operator_console_v2_3_contract

ROOT = Path(__file__).resolve().parents[3]
CONSOLE_ROOT = ROOT / "console"
SNAPSHOT = ROOT / "tests" / "enterprise/contracts/snapshots/ui_v2_3.json"


def test_console_e2e_contract_snapshot_is_present() -> None:
    assert SNAPSHOT.is_file()
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert payload["contract"] == "OperatorConsoleV2_3"


def test_console_e2e_all_contract_source_files_exist() -> None:
    for relative in CONSOLE_SOURCE_FILES:
        assert (CONSOLE_ROOT / relative).is_file(), relative


def test_console_e2e_vitest_suites_exist() -> None:
    contract = operator_console_v2_3_contract()
    for relative in contract["vitest_suites"]:
        assert (CONSOLE_ROOT / relative).is_file(), relative


def test_console_e2e_offline_python_suites_exist() -> None:
    contract = operator_console_v2_3_contract()
    for relative in contract["offline_python_suites"]:
        assert (ROOT / relative).is_file(), relative


def test_console_e2e_routes_cover_operator_workflows() -> None:
    contract = operator_console_v2_3_contract()
    routes = contract["console_routes"]
    assert "/t/{tenantId}/runs" in routes
    assert "/t/{tenantId}/approvals" in routes
    assert "/t/{tenantId}/eval" in routes
    assert "/t/{tenantId}/runs/{runId}/evidence" in routes
