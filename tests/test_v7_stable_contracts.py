"""Tests for v7.0.0 stable contract cut."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from safecode.agent.read_tools import SEARCH_SYMBOL_SPEC
from safecode.cli_ops import _STABLE_CONTRACTS
from safecode.config import SafeCodeConfig
from safecode.context.budget import ModelContextProfile, effective_context_budget

_DOCS = Path(__file__).parent.parent / "docs" / "public-contracts.md"
_POLICY = Path(__file__).parent.parent / "docs" / "versioning-policy.md"


def test_search_symbol_promoted_to_stable_read_tool() -> None:
    assert SEARCH_SYMBOL_SPEC.experimental is False
    assert SEARCH_SYMBOL_SPEC.requires_approval is False
    assert SEARCH_SYMBOL_SPEC.audit_event_type == "tool_call_read"
    assert SEARCH_SYMBOL_SPEC.input_schema["required"] == ["name"]


def test_model_context_budget_contract_invariants() -> None:
    mock_budget = effective_context_budget(SafeCodeConfig())
    assert mock_budget.max_bytes == 40_000

    deepseek_cfg = SafeCodeConfig()
    deepseek_cfg.llm.provider = "deepseek"
    deepseek_cfg.llm.model = "deepseek-v4-flash"
    profile = ModelContextProfile.infer(deepseek_cfg.llm.provider, deepseek_cfg.llm.model)
    budget = effective_context_budget(deepseek_cfg)

    assert profile is not None
    assert profile.safe_input_ratio == 0.70
    assert profile.compact_threshold_ratio == 0.60
    assert budget.max_tokens == profile.safe_input_tokens


def test_version_json_lists_v7_contracts() -> None:
    from safecode.cli_ops import version as version_cmd

    output_buf = StringIO()
    with patch("builtins.print", side_effect=lambda s: output_buf.write(s + "\n")):
        version_cmd(json_output=True)

    data = json.loads(output_buf.getvalue())
    contracts = set(data["data"]["stable_contracts"])
    assert contracts == set(_STABLE_CONTRACTS)
    for name in {
        "project_memory_store_shape",
        "search_symbol",
        "model_context_budget_profile",
    }:
        assert name in contracts


def test_public_contracts_has_v7_sections() -> None:
    text = _DOCS.read_text(encoding="utf-8")
    assert "## v7.0.0 Contract Promotions" in text
    assert "### 21. Project Memory Store Shape" in text
    assert "### 22. `search_symbol` Native Tool Contract" in text
    assert "### 23. Model Context Budget Profile Contract" in text
    assert "Zero breaking changes" in text


def test_versioning_policy_records_v7_cut() -> None:
    text = _POLICY.read_text(encoding="utf-8")
    assert "## v7.0 Contract Churn Budget" in text
    assert "23 stable contracts" in text
    assert "Zero v6.0 breaking changes" in text

