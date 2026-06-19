"""Deterministic transcript snapshot tests for enterprise demos (v3.2.2-T1)."""

from __future__ import annotations

import shutil
from pathlib import Path

from safecode.enterprise.demo.pr_review import run_pr_review_offline_demo
from safecode.enterprise.demo.redactor import redact_transcript

_ROOT = Path(__file__).resolve().parents[3]
_SNAPSHOT = (
    _ROOT / "examples" / "enterprise" / "demos" / "v3.2" / "transcripts" / "pr-review.txt"
)


def _seed_demo_root(tmp_path: Path) -> Path:
    shutil.copytree(_ROOT / "examples" / "enterprise", tmp_path / "examples" / "enterprise")
    return tmp_path


def test_pr_review_transcript_matches_snapshot(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    raw = run_pr_review_offline_demo(root)
    redacted = redact_transcript(raw)
    expected = _SNAPSHOT.read_text(encoding="utf-8")
    assert redacted == expected


def test_redactor_strips_volatile_fields() -> None:
    sample = (
        "run-demoprreview at 2026-06-19T12:34:56Z /Users/demo/project "
        "approval-run-demoprreview grant-grant123 "
        "Bearer xxxxxxxxxxxxxxxxxxxx hostname.local"
    )
    redacted = redact_transcript(sample)
    assert "run-demoprreview" not in redacted
    assert "/Users/" not in redacted
    assert "xxxxxxxxxxxxxxxxxxxx" not in redacted
    assert "hostname.local" not in redacted
    assert "<run-id>" in redacted
    assert "<timestamp>" in redacted
    assert "<path>" in redacted


def test_redactor_strips_sha256_hash() -> None:
    digest = "ab" * 32
    redacted = redact_transcript(f"audit_chain_head: {digest}")
    assert digest not in redacted
    assert "<hash>" in redacted
