"""Tests for v7.0.0 stable contract cut."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from safecode.agent.read_tools import SEARCH_SYMBOL_SPEC
from safecode.cli_ops import _STABLE_CONTRACTS
from safecode.config import SafeCodeConfig
from safecode.context.budget import ModelContextProfile, effective_context_budget

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
