"""Tests for v5.8.0 cost guardrails — budget caps, fallback, /budget."""

import tempfile
from pathlib import Path

import pytest

from safecode.config import CostConfig, SafeCodeConfig, merge_trusted_config
from safecode.llm.cost import (
    BudgetCheckResult,
    TokenUsage,
    check_budget,
    check_cost_fallback,
    render_budget_summary,
)


# ---------------------------------------------------------------------------
# BudgetCheckResult
# ---------------------------------------------------------------------------


def test_budget_ok_when_cap_none():
    result = check_budget(TokenUsage(total_tokens=50000), cap=None)
    assert result.status == "ok"


def test_budget_ok_below_90pct():
    result = check_budget(TokenUsage(total_tokens=1000), cap=20000)
    assert result.status == "ok"


def test_budget_warning_at_90pct():
    result = check_budget(TokenUsage(total_tokens=18000), cap=20000)
    assert result.status == "warning_90pct"
    assert "90%" in result.message or "90" in result.message


def test_budget_warning_slightly_above_90():
    result = check_budget(TokenUsage(total_tokens=19000), cap=20000)
    assert result.status == "warning_90pct"


def test_budget_cap_hit_at_100pct():
    result = check_budget(TokenUsage(total_tokens=20000), cap=20000)
    assert result.status == "cap_hit"
    assert "continue" in result.message.lower()


def test_budget_cap_hit_above():
    result = check_budget(TokenUsage(total_tokens=25000), cap=20000)
    assert result.status == "cap_hit"


def test_budget_extension_raises_effective_cap():
    result = check_budget(TokenUsage(total_tokens=21000), cap=20000, extension_active=True)
    # effective cap = 20000 * 1.1 = 22000, so 21000 is below that
    assert result.status == "warning_90pct", f"Got {result.status} at tokens=21000 with extension"


def test_budget_extension_still_hit():
    result = check_budget(TokenUsage(total_tokens=23000), cap=20000, extension_active=True)
    assert result.status == "cap_hit"


# ---------------------------------------------------------------------------
# Cost fallback
# ---------------------------------------------------------------------------


def test_fallback_disabled_when_none():
    usage = TokenUsage(cost_usd=0.50)
    assert check_cost_fallback(usage, fallback_usd=None) is False


def test_fallback_not_triggered_below_threshold():
    usage = TokenUsage(cost_usd=0.05)
    assert check_cost_fallback(usage, fallback_usd=0.10) is False


def test_fallback_triggered_at_threshold():
    usage = TokenUsage(cost_usd=0.10)
    assert check_cost_fallback(usage, fallback_usd=0.10) is True


def test_fallback_triggered_above_threshold():
    usage = TokenUsage(cost_usd=0.50)
    assert check_cost_fallback(usage, fallback_usd=0.10) is True


def test_fallback_no_cost_estimate():
    usage = TokenUsage(cost_usd=None)
    assert check_cost_fallback(usage, fallback_usd=0.10) is False


# ---------------------------------------------------------------------------
# render_budget_summary
# ---------------------------------------------------------------------------


def test_render_budget_summary_unlimited():
    result = render_budget_summary(TokenUsage(total_tokens=500), cap=None)
    assert "unlimited" in result


def test_render_budget_summary_with_cap():
    result = render_budget_summary(TokenUsage(total_tokens=1000), cap=20000)
    assert "20,000" in result
    assert "1,000" in result


def test_render_budget_summary_with_cost():
    result = render_budget_summary(TokenUsage(total_tokens=1000, cost_usd=0.03), cap=20000)
    assert "0.03" in result or "$0" in result


def test_render_budget_summary_unknown_cost():
    result = render_budget_summary(TokenUsage(total_tokens=1000), cap=None)
    assert "unknown" in result


# ---------------------------------------------------------------------------
# CostConfig model
# ---------------------------------------------------------------------------


class TestCostConfigModel:
    def test_default_max_tokens_is_none(self):
        cc = CostConfig()
        assert cc.max_tokens_per_session is None

    def test_default_fallback_is_none(self):
        cc = CostConfig()
        assert cc.fallback_on_usd is None

    def test_can_set_cap(self):
        cc = CostConfig(max_tokens_per_session=20000)
        assert cc.max_tokens_per_session == 20000

    def test_can_set_fallback(self):
        cc = CostConfig(fallback_on_usd=0.10)
        assert cc.fallback_on_usd == 0.10


# ---------------------------------------------------------------------------
# Config merge: project can only lower cap
# ---------------------------------------------------------------------------


class TestCostConfigMerge:
    def test_user_unlimited_project_sets_cap(self):
        user = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=None))
        project = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=10000))
        merged = merge_trusted_config(user, project)
        assert merged.cost.max_tokens_per_session == 10000

    def test_user_cap_100k_project_50k_merges_to_50k(self):
        user = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=100000))
        project = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=50000))
        merged = merge_trusted_config(user, project)
        assert merged.cost.max_tokens_per_session == 50000

    def test_user_cap_50k_project_unlimited_keeps_50k(self):
        user = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=50000))
        project = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=None))
        merged = merge_trusted_config(user, project)
        assert merged.cost.max_tokens_per_session == 50000

    def test_project_cannot_raise_above_user_cap(self):
        user = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=10000))
        project = SafeCodeConfig(cost=CostConfig(max_tokens_per_session=50000))
        merged = merge_trusted_config(user, project)
        # Should stay at 10000 (user cap), not 50000
        assert merged.cost.max_tokens_per_session == 10000

    def test_fallback_merges_to_lower(self):
        user = SafeCodeConfig(cost=CostConfig(fallback_on_usd=0.50))
        project = SafeCodeConfig(cost=CostConfig(fallback_on_usd=0.10))
        merged = merge_trusted_config(user, project)
        assert merged.cost.fallback_on_usd == 0.10

    def test_fallback_project_cannot_raise(self):
        user = SafeCodeConfig(cost=CostConfig(fallback_on_usd=0.10))
        project = SafeCodeConfig(cost=CostConfig(fallback_on_usd=0.50))
        merged = merge_trusted_config(user, project)
        assert merged.cost.fallback_on_usd == 0.10
