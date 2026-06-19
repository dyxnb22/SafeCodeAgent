"""Operator Console v2.3 public contract snapshot tests (v2.3.5-T1)."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.enterprise.contracts.v2_3 import assert_ui_snapshot_safe, operator_console_v2_3_contract

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "ui_v2_3.json"


def _load_snapshot() -> dict:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def test_ui_v2_3_snapshot_matches_live() -> None:
    expected = _load_snapshot()
    live = operator_console_v2_3_contract()
    assert live == expected, (
        "v2.3 Operator Console contract drift; update tests/enterprise/contracts/snapshots/ui_v2_3.json"
    )


def test_ui_v2_3_snapshot_file_exists() -> None:
    assert _SNAPSHOT.is_file()


def test_ui_v2_3_snapshot_scrubs_secrets_and_host_paths() -> None:
    assert_ui_snapshot_safe(operator_console_v2_3_contract())


def test_ui_v2_3_timeline_sections_match_markdown_renderer() -> None:
    from safecode.enterprise.trace.render_markdown import SECTION_ORDER

    live = operator_console_v2_3_contract()
    assert live["timeline_sections"] == list(SECTION_ORDER)


def test_ui_v2_3_write_paths_require_idempotency_header() -> None:
    live = operator_console_v2_3_contract()
    assert "Idempotency-Key" in live["required_headers"]["write"]
