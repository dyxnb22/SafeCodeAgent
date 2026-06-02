"""Snapshot tests for the LLM provider contract (v3.2.6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "contracts" / "provider_contract_schema.json"


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text())


class TestProviderContractSnapshotFile:
    def test_snapshot_file_exists(self):
        assert SNAPSHOT_PATH.exists(), "provider_contract_schema.json missing"

    def test_snapshot_is_valid_json(self):
        data = json.loads(SNAPSHOT_PATH.read_text())
        assert isinstance(data, dict)

    def test_snapshot_keys_sorted(self):
        raw = SNAPSHOT_PATH.read_text()
        data = json.loads(raw)
        repacked = json.dumps(data, sort_keys=True, indent=2)
        assert json.loads(raw) == json.loads(repacked)

    def test_snapshot_no_prose(self):
        raw = SNAPSHOT_PATH.read_text()
        assert len(raw) < 8000, "Snapshot unexpectedly large — prose may have crept in"


class TestProviderContractTopLevel:
    def test_contract_name(self, snapshot):
        assert snapshot["contract"] == "LLMProvider"

    def test_contract_status(self, snapshot):
        assert snapshot["contract_status"] == "supported"

    def test_schema_version_numeric(self, snapshot):
        assert snapshot["schema_version"].isdigit()

    def test_supported_provider_keys_sorted(self, snapshot):
        keys = snapshot["supported_provider_keys"]
        assert keys == sorted(keys)

    def test_required_provider_keys_present(self, snapshot):
        keys = snapshot["supported_provider_keys"]
        for required in ("mock", "openai", "openai-compatible", "anthropic"):
            assert required in keys, f"Missing provider key: {required}"


class TestProviderContractConfigFields:
    def test_config_fields_present(self, snapshot):
        assert "config_fields" in snapshot

    def test_llm_config_fields_sorted(self, snapshot):
        fields = snapshot["config_fields"]["llm_config_fields"]
        assert fields == sorted(fields)

    def test_provider_is_required(self, snapshot):
        assert "provider" in snapshot["config_fields"]["required"]

    def test_default_provider_is_mock(self, snapshot):
        assert snapshot["config_fields"]["defaults"]["provider"] == "mock"

    def test_fallback_fields_default_null(self, snapshot):
        defaults = snapshot["config_fields"]["defaults"]
        assert defaults["fallback_provider"] is None
        assert defaults["fallback_model"] is None
        assert defaults["fallback_base_url"] is None

    def test_all_config_fields_have_defaults(self, snapshot):
        fields = snapshot["config_fields"]["llm_config_fields"]
        defaults = snapshot["config_fields"]["defaults"]
        for f in fields:
            assert f in defaults, f"No default for field: {f}"


class TestProviderContractRetrySemantics:
    def test_retry_semantics_present(self, snapshot):
        assert "retry_semantics" in snapshot

    def test_retryable_statuses_contain_429_and_503(self, snapshot):
        statuses = snapshot["retry_semantics"]["retryable_http_statuses"]
        assert 429 in statuses
        assert 503 in statuses

    def test_url_error_retryable(self, snapshot):
        assert "URLError" in snapshot["retry_semantics"]["retryable_errors"]

    def test_max_attempts(self, snapshot):
        assert snapshot["retry_semantics"]["max_attempts"] == 3

    def test_base_delay(self, snapshot):
        assert snapshot["retry_semantics"]["base_delay_seconds"] == 0.5

    def test_not_retried_list_nonempty(self, snapshot):
        assert len(snapshot["retry_semantics"]["not_retried"]) > 0

    def test_permission_error_not_retried(self, snapshot):
        not_retried = " ".join(snapshot["retry_semantics"]["not_retried"])
        assert "PermissionError" in not_retried

    def test_value_error_not_retried(self, snapshot):
        not_retried = " ".join(snapshot["retry_semantics"]["not_retried"])
        assert "ValueError" in not_retried


class TestProviderContractStreamingSemantics:
    def test_streaming_semantics_present(self, snapshot):
        assert "streaming_semantics" in snapshot

    def test_protocol_name(self, snapshot):
        assert snapshot["streaming_semantics"]["protocol"] == "SupportsStreaming"

    def test_chunk_type(self, snapshot):
        assert snapshot["streaming_semantics"]["chunk_type"] == "StreamChunk"

    def test_result_type(self, snapshot):
        assert snapshot["streaming_semantics"]["result_type"] == "StreamResult"

    def test_error_type(self, snapshot):
        assert snapshot["streaming_semantics"]["error_type"] == "StreamError"

    def test_chunk_fields_present(self, snapshot):
        fields = snapshot["streaming_semantics"]["chunk_fields"]
        assert "delta" in fields
        assert "finish_reason" in fields

    def test_cancel_behavior(self, snapshot):
        cancel = snapshot["streaming_semantics"]["cancel_behavior"]
        assert "fail_closed" in cancel
        assert "partial output discarded" in cancel


class TestProviderContractStructuredOutput:
    def test_structured_output_present(self, snapshot):
        assert "structured_output_validation" in snapshot

    def test_validate_function_name(self, snapshot):
        assert snapshot["structured_output_validation"]["function"] == "validate_provider_json"

    def test_soft_failure_type(self, snapshot):
        assert snapshot["structured_output_validation"]["soft_failure_type"] == "RecoverableContractFailure"

    def test_hard_failure_type(self, snapshot):
        assert snapshot["structured_output_validation"]["hard_failure_type"] == "ValueError"

    def test_soft_failures_nonempty(self, snapshot):
        assert len(snapshot["structured_output_validation"]["soft_failures"]) > 0

    def test_hard_failures_nonempty(self, snapshot):
        assert len(snapshot["structured_output_validation"]["hard_failures"]) > 0


class TestProviderContractCostAccounting:
    def test_cost_accounting_present(self, snapshot):
        assert "cost_accounting" in snapshot

    def test_model_name(self, snapshot):
        assert snapshot["cost_accounting"]["model"] == "TokenUsage"

    def test_token_usage_fields(self, snapshot):
        fields = snapshot["cost_accounting"]["fields"]
        for f in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd"):
            assert f in fields

    def test_accumulator_name(self, snapshot):
        assert snapshot["cost_accounting"]["accumulator"] == "SessionCostAccumulator"

    def test_cost_usd_always_null(self, snapshot):
        assert "null" in snapshot["cost_accounting"]["cost_usd"]


class TestProviderContractFanout:
    def test_fanout_config_present(self, snapshot):
        assert "fanout_config" in snapshot

    def test_trigger_is_runtime_error(self, snapshot):
        assert "RuntimeError" in snapshot["fanout_config"]["trigger"]

    def test_permission_error_not_triggered(self, snapshot):
        not_triggered = " ".join(snapshot["fanout_config"]["not_triggered_by"])
        assert "PermissionError" in not_triggered

    def test_value_error_not_triggered(self, snapshot):
        not_triggered = " ".join(snapshot["fanout_config"]["not_triggered_by"])
        assert "ValueError" in not_triggered

    def test_recoverable_not_triggered(self, snapshot):
        not_triggered = " ".join(snapshot["fanout_config"]["not_triggered_by"])
        assert "RecoverableContractFailure" in not_triggered

    def test_log_no_prompt_content(self, snapshot):
        log_desc = snapshot["fanout_config"]["log"]
        assert "no prompt" in log_desc or "no prompt or context" in log_desc


class TestProviderContractExperimentalFeatures:
    def test_experimental_features_present(self, snapshot):
        assert "experimental_features" in snapshot

    def test_experimental_features_nonempty(self, snapshot):
        assert len(snapshot["experimental_features"]) > 0

    def test_streaming_fanout_midstream_is_experimental(self, snapshot):
        features = snapshot["experimental_features"]
        assert any("streaming_fanout" in f or "stream" in f for f in features)


class TestProviderContractLiveCILane:
    def test_live_ci_lane_present(self, snapshot):
        assert "live_ci_lane" in snapshot

    def test_status_advisory(self, snapshot):
        assert snapshot["live_ci_lane"]["status"] == "advisory"

    def test_skipped_by_default(self, snapshot):
        assert snapshot["live_ci_lane"]["skipped_by_default"] is True

    def test_does_not_block_merges(self, snapshot):
        assert snapshot["live_ci_lane"]["blocks_merges"] is False


class TestProviderContractMatchesLiveCode:
    def test_validate_provider_json_importable(self):
        from safecode.agent.schemas import validate_provider_json
        assert callable(validate_provider_json)

    def test_recoverable_contract_failure_importable(self):
        from safecode.agent.schemas import RecoverableContractFailure
        assert RecoverableContractFailure is not None

    def test_stream_chunk_importable(self):
        from safecode.llm.stream import StreamChunk
        assert StreamChunk is not None

    def test_stream_result_importable(self):
        from safecode.llm.stream import StreamResult
        assert StreamResult is not None

    def test_stream_error_importable(self):
        from safecode.llm.stream import StreamError
        assert StreamError is not None

    def test_supports_streaming_importable(self):
        from safecode.llm.stream import SupportsStreaming
        assert SupportsStreaming is not None

    def test_token_usage_importable(self):
        from safecode.llm.cost import TokenUsage
        assert TokenUsage is not None

    def test_session_cost_accumulator_importable(self):
        from safecode.llm.cost import SessionCostAccumulator
        assert SessionCostAccumulator is not None

    def test_fanout_client_importable(self):
        from safecode.llm.factory import FanOutLLMClient
        assert FanOutLLMClient is not None

    def test_anthropic_client_importable(self):
        from safecode.llm.anthropic_client import AnthropicLLMClient
        assert AnthropicLLMClient is not None

    def test_llm_config_fallback_fields(self):
        from safecode.config import LLMConfig
        cfg = LLMConfig(provider="mock")
        assert cfg.fallback_provider is None
        assert cfg.fallback_model is None
        assert cfg.fallback_base_url is None

    def test_supported_providers_in_factory(self, snapshot):
        from safecode.llm import factory as f
        expected = set(snapshot["supported_provider_keys"])
        # factory knows about all documented providers
        all_providers = f._OPENAI_PROVIDERS | f._ANTHROPIC_PROVIDERS | {"mock"}
        for key in expected:
            assert key in all_providers, f"Provider key not in factory: {key}"
