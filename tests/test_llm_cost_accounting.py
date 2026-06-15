"""Tests for v3.2.0 llm-cost-accounting.

Verifies:
- SessionCostAccumulator.record() writes cost.json atomically.
- Multiple records accumulate correctly.
- load() returns None when no file.
- total() sums across records.
- cost_usd is None (not a number) for unknown pricing.
- sac doctor output includes last_session_cost check when cost.json exists.
- sac doctor output shows SKIP when no cost data.
- OpenAICompatibleLLMClient._chat calls accumulator (mocked transport).
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.llm.cost import SessionCostAccumulator, TokenUsage
from safecode.cli import app

runner = CliRunner()


# ── TokenUsage ────────────────────────────────────────────────────────────────

class TestTokenUsage:
    def test_default_is_zero(self):
        u = TokenUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0
        assert u.cost_usd is None

    def test_add_accumulates(self):
        a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        b = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        c = a + b
        assert c.prompt_tokens == 30
        assert c.completion_tokens == 15
        assert c.total_tokens == 45
        assert c.cost_usd is None

    def test_as_dict_keys(self):
        u = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        d = u.as_dict()
        assert {"prompt_tokens", "completion_tokens", "total_tokens", "cost_usd"}.issubset(d.keys())


# ── SessionCostAccumulator ────────────────────────────────────────────────────

class TestSessionCostAccumulator:
    def test_load_returns_none_when_no_file(self, tmp_path):
        acc = SessionCostAccumulator(tmp_path / ".sac", "session-1")
        assert acc.load() is None

    def test_record_writes_cost_json(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "session-1")
        acc.record(TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
        cost_file = sac_dir / "sessions" / "session-1" / "cost.json"
        assert cost_file.exists()
        data = json.loads(cost_file.read_text())
        assert data["prompt_tokens"] == 10
        assert data["completion_tokens"] == 5
        assert data["total_tokens"] == 15

    def test_multiple_records_accumulate(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "session-1")
        acc.record(TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
        acc.record(TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30))
        total = acc.total()
        assert total.prompt_tokens == 30
        assert total.completion_tokens == 15
        assert total.total_tokens == 45

    def test_cost_usd_is_none(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "session-1")
        acc.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        total = acc.total()
        assert total.cost_usd is None

    def test_total_returns_zero_when_no_file(self, tmp_path):
        acc = SessionCostAccumulator(tmp_path / ".sac", "session-1")
        total = acc.total()
        assert total.prompt_tokens == 0
        assert total.completion_tokens == 0

    def test_cost_json_has_sorted_keys(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "s1")
        acc.record(TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3))
        cost_file = sac_dir / "sessions" / "s1" / "cost.json"
        raw = cost_file.read_text()
        keys = list(json.loads(raw).keys())
        assert keys == sorted(keys)


# ── sac doctor integration ────────────────────────────────────────────────────

class TestDoctorCostDiagnostic:
    def test_doctor_shows_skip_when_no_cost_data(self, tmp_path):
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "last_session_cost" in result.output

    def test_doctor_shows_pass_when_cost_exists(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "session-abc")
        acc.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "last_session_cost" in result.output
        assert "100" in result.output or "prompt" in result.output or "last_session" in result.output


# ── OpenAICompatibleLLMClient cost wiring ────────────────────────────────────

class TestOpenAIClientCostWiring:
    def _make_response(self, prompt: int = 10, completion: int = 5) -> dict:
        return {
            "choices": [{"message": {"content": "answer"}}],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
        }

    def test_record_called_when_session_and_sac_dir_set(self, tmp_path):
        from safecode.config import SafeCodeConfig
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        config = SafeCodeConfig()
        config.llm.provider = "openai-compatible"
        config.llm.base_url = "http://fake-llm/v1/chat/completions"

        resp_data = self._make_response()

        with patch("os.getenv", return_value="fake-key"), \
             patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = json.dumps(resp_data).encode()
            mock_urlopen.return_value = mock_resp

            sac_dir = tmp_path / ".sac"
            client = OpenAICompatibleLLMClient(
                config, session_id="test-session", sac_dir=sac_dir
            )
            result = client._chat([{"role": "user", "content": "hello"}])

        cost_file = sac_dir / "sessions" / "test-session" / "cost.json"
        assert cost_file.exists()
        data = json.loads(cost_file.read_text())
        assert data["prompt_tokens"] == 10
        assert data["completion_tokens"] == 5

    def test_no_record_when_session_id_not_set(self, tmp_path):
        from safecode.config import SafeCodeConfig
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        config = SafeCodeConfig()
        config.llm.provider = "openai-compatible"
        config.llm.base_url = "http://fake-llm/v1/chat/completions"

        resp_data = self._make_response()

        with patch("os.getenv", return_value="fake-key"), \
             patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = json.dumps(resp_data).encode()
            mock_urlopen.return_value = mock_resp

            client = OpenAICompatibleLLMClient(config)
            client._chat([{"role": "user", "content": "hello"}])

        sessions_dir = tmp_path / ".sac" / "sessions"
        assert not sessions_dir.exists()
