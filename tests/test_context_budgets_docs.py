"""Tests for v3.10.2 context-budgets.md documentation.

Verifies:
- docs/context-budgets.md exists with required sections
- Numbers referenced tie back to existing code (ContextBudget, ContextBudgetPacker)
- ContextBudget defaults match what the docs claim
- p50 table references match available bench snapshot fixture names
- No unsupported performance claims
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.context.budget import (
    TOKEN_CHAR_RATIO,
    ContextBudget,
    ContextBudgetPacker,
    ContextBudgetReport,
    ContextSource,
)
from safecode.config import SafeCodeConfig

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "context-budgets.md"
BENCH_DIR = ROOT / "tests" / "snapshots" / "bench"


# ── Document existence and structure ─────────────────────────────────────


class TestContextBudgetsDocExists:
    def test_doc_file_exists(self):
        assert DOC.is_file(), "docs/context-budgets.md must exist"

    def test_doc_has_overview_section(self):
        text = DOC.read_text(encoding="utf-8")
        assert "## Overview" in text or "overview" in text.lower()

    def test_doc_has_core_classes_section(self):
        text = DOC.read_text(encoding="utf-8")
        assert "ContextBudget" in text
        assert "ContextBudgetPacker" in text

    def test_doc_mentions_default_40000(self):
        text = DOC.read_text(encoding="utf-8")
        assert "40,000" in text or "40_000" in text or "40000" in text

    def test_doc_mentions_token_char_ratio(self):
        text = DOC.read_text(encoding="utf-8")
        assert "token" in text.lower()

    def test_doc_mentions_p50_section(self):
        text = DOC.read_text(encoding="utf-8")
        assert "p50" in text.lower() or "language" in text.lower()

    def test_doc_mentions_bench_output(self):
        text = DOC.read_text(encoding="utf-8")
        assert "bench" in text.lower()

    def test_doc_mentions_safety_notes(self):
        text = DOC.read_text(encoding="utf-8")
        assert "safety" in text.lower() or "never" in text.lower()

    def test_doc_has_reproducibility_note(self):
        text = DOC.read_text(encoding="utf-8")
        assert "reproduc" in text.lower() or "baseline" in text.lower()

    def test_doc_does_not_claim_unsupported_performance(self):
        text = DOC.read_text(encoding="utf-8")
        forbidden = ["guaranteed sub-second", "100x faster", "10x throughput"]
        for claim in forbidden:
            assert claim.lower() not in text.lower(), f"Unsupported claim: {claim!r}"


# ── Code matches documented defaults ────────────────────────────────────


class TestContextBudgetCodeMatches:
    def test_default_max_context_chars_is_40000(self):
        config = SafeCodeConfig()
        assert config.max_context_chars == 40_000

    def test_token_char_ratio_is_3_5(self):
        # B4 fix: ratio corrected from 4 to 3.5 (code is denser than prose).
        assert TOKEN_CHAR_RATIO == 3.5

    def test_context_budget_from_max_chars(self):
        import math
        budget = ContextBudget.from_max_chars(40_000)
        assert budget.max_bytes == 40_000
        assert budget.max_tokens == math.ceil(40_000 / 3.5)  # B4 fix: ratio 3.5

    def test_context_budget_packer_respects_limit(self):
        budget = ContextBudget(max_bytes=100)
        packer = ContextBudgetPacker(budget)
        context = {"task": "x" * 200}
        packed, report = packer.pack(context)
        assert len(packed["task"].encode("utf-8")) <= 100

    def test_context_budget_report_has_required_fields(self):
        budget = ContextBudget.from_max_chars(1000)
        packer = ContextBudgetPacker(budget)
        _, report = packer.pack({"task": "hello world"})
        d = report.to_dict()
        assert "max_bytes" in d
        assert "bytes_used" in d
        assert "tokens_estimated" in d
        assert "sources" in d

    def test_context_budget_never_raises(self):
        budget = ContextBudget(max_bytes=0)
        packer = ContextBudgetPacker(budget)
        packed, report = packer.pack({"task": "some text"})
        # Should return empty string without raising


# ── Bench snapshots match doc fixture names ──────────────────────────────


class TestContextBudgetsDocBenchCoverage:
    DOCUMENTED_FIXTURES = [
        "python-function-fix",
        "config-update-fix",
        "docs-edit",
        "shell-readonly-check",
        "test-assertion-fix",
        "import-cleanup",
    ]

    def test_bench_snapshot_dir_exists(self):
        assert BENCH_DIR.is_dir(), (
            "tests/snapshots/bench/ must exist; run: sac eval --mode bench"
        )

    def test_documented_fixture_names_have_snapshots(self):
        for name in self.DOCUMENTED_FIXTURES:
            path = BENCH_DIR / f"{name}.json"
            assert path.exists(), (
                f"Bench snapshot for {name!r} not found at {path}. "
                f"Run: sac eval --mode bench"
            )

    def test_snapshots_are_valid_json(self):
        for name in self.DOCUMENTED_FIXTURES:
            path = BENCH_DIR / f"{name}.json"
            if path.exists():
                data = json.loads(path.read_text())
                assert "fixture_name" in data
                assert "step_count" in data

    def test_snapshots_show_passing_results(self):
        for name in self.DOCUMENTED_FIXTURES:
            path = BENCH_DIR / f"{name}.json"
            if path.exists():
                data = json.loads(path.read_text())
                assert data.get("passed") is True, (
                    f"Snapshot for {name!r} shows a failing result"
                )

    def test_doc_mentions_all_documented_fixtures(self):
        text = DOC.read_text(encoding="utf-8")
        for name in self.DOCUMENTED_FIXTURES:
            assert name in text, f"docs/context-budgets.md must mention fixture {name!r}"
