"""Extended retry, timeout, and rate-limit tests (v4.10.3)."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from safecode.llm.retry import (
    RateLimitError,
    _MAX_RETRY_AFTER_SECONDS,
    _RETRYABLE_HTTP_STATUSES,
    retry_call,
)


# ---------------------------------------------------------------------------
# Retryable status codes
# ---------------------------------------------------------------------------


class TestRetryableStatuses:
    def test_408_is_retryable(self):
        assert 408 in _RETRYABLE_HTTP_STATUSES

    def test_429_is_retryable(self):
        assert 429 in _RETRYABLE_HTTP_STATUSES

    def test_502_is_retryable(self):
        assert 502 in _RETRYABLE_HTTP_STATUSES

    def test_503_is_retryable(self):
        assert 503 in _RETRYABLE_HTTP_STATUSES

    def test_504_is_retryable(self):
        assert 504 in _RETRYABLE_HTTP_STATUSES

    def test_400_not_retryable(self):
        assert 400 not in _RETRYABLE_HTTP_STATUSES

    def test_500_not_retryable(self):
        assert 500 not in _RETRYABLE_HTTP_STATUSES

    def test_404_not_retryable(self):
        assert 404 not in _RETRYABLE_HTTP_STATUSES


# ---------------------------------------------------------------------------
# RateLimitError
# ---------------------------------------------------------------------------


class TestRateLimitError:
    def test_rate_limit_error_is_runtime_error(self):
        assert issubclass(RateLimitError, RuntimeError)

    def test_rate_limit_error_raised_on_exhausted_429(self):
        def always_429():
            err = urllib.error.HTTPError(url="u", code=429, msg="Too Many Requests",
                                         hdrs=None, fp=None)
            raise err

        with pytest.raises(RateLimitError):
            retry_call(always_429, max_attempts=2, base_delay=0.0)

    def test_rate_limit_error_not_raised_on_other_codes(self):
        def always_503():
            err = urllib.error.HTTPError(url="u", code=503, msg="Service Unavailable",
                                         hdrs=None, fp=None)
            raise err

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            retry_call(always_503, max_attempts=2, base_delay=0.0)
        assert exc_info.value.code == 503

    def test_rate_limit_error_message_has_no_prompt_content(self):
        def always_429():
            raise urllib.error.HTTPError(url="u", code=429, msg="Rate limited",
                                          hdrs=None, fp=None)
        try:
            retry_call(always_429, max_attempts=1, base_delay=0.0)
        except RateLimitError as exc:
            assert "secret-prompt-content" not in str(exc)

    def test_max_retry_after_cap_constant(self):
        assert _MAX_RETRY_AFTER_SECONDS == 30.0

    def test_retry_after_capped_at_30_seconds(self):
        """Retry-After of 999s is capped to _MAX_RETRY_AFTER_SECONDS."""
        sleep_calls: list[float] = []

        def always_429():
            raise urllib.error.HTTPError(url="u", code=429, msg="x", hdrs=None, fp=None)

        with patch("safecode.llm.retry.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            try:
                retry_call(
                    always_429,
                    max_attempts=2,
                    base_delay=0.0,
                    get_retry_after=lambda: 999.0,
                )
            except (RateLimitError, urllib.error.HTTPError):
                pass

        assert all(s <= _MAX_RETRY_AFTER_SECONDS for s in sleep_calls), sleep_calls

    def test_retry_after_honored_when_below_cap(self):
        sleep_calls: list[float] = []
        attempts = [0]

        def fn():
            attempts[0] += 1
            if attempts[0] == 1:
                raise urllib.error.HTTPError(url="u", code=429, msg="x", hdrs=None, fp=None)
            return "ok"

        with patch("safecode.llm.retry.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            result = retry_call(fn, max_attempts=3, base_delay=0.0, get_retry_after=lambda: 5.0)

        assert result == "ok"
        # At least one sleep should be >= 5.0 (the Retry-After value)
        assert any(s >= 5.0 for s in sleep_calls)


# ---------------------------------------------------------------------------
# Retrying HTTP codes 408, 502, 504
# ---------------------------------------------------------------------------


class TestExtendedRetryableCodes:
    def _retry_n_then_succeed(self, code: int, n: int):
        calls = [0]

        def fn():
            calls[0] += 1
            if calls[0] <= n:
                raise urllib.error.HTTPError(url="u", code=code, msg="x", hdrs=None, fp=None)
            return "ok"

        with patch("safecode.llm.retry.time.sleep"):
            return retry_call(fn, max_attempts=n + 1, base_delay=0.0)

    def test_408_retried_then_success(self):
        assert self._retry_n_then_succeed(408, 1) == "ok"

    def test_502_retried_then_success(self):
        assert self._retry_n_then_succeed(502, 1) == "ok"

    def test_504_retried_then_success(self):
        assert self._retry_n_then_succeed(504, 1) == "ok"

    def test_400_not_retried(self):
        def always_400():
            raise urllib.error.HTTPError(url="u", code=400, msg="Bad Request",
                                          hdrs=None, fp=None)

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            retry_call(always_400, max_attempts=3, base_delay=0.0)
        assert exc_info.value.code == 400


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------


class TestProgressCallback:
    def test_request_started_called(self):
        stages: list[str] = []

        def fn():
            return "ok"

        retry_call(fn, progress_callback=stages.append)
        assert "request_started" in stages

    def test_response_received_called_on_success(self):
        stages: list[str] = []

        retry_call(lambda: "ok", progress_callback=stages.append)
        assert "response_received" in stages

    def test_retrying_called_on_url_error(self):
        stages: list[str] = []
        calls = [0]

        def fn():
            calls[0] += 1
            if calls[0] == 1:
                raise urllib.error.URLError("connection refused")
            return "ok"

        with patch("safecode.llm.retry.time.sleep"):
            retry_call(fn, max_attempts=3, base_delay=0.0, progress_callback=stages.append)
        assert "retrying" in stages

    def test_rate_limited_called_on_429(self):
        stages: list[str] = []
        calls = [0]

        def fn():
            calls[0] += 1
            if calls[0] == 1:
                raise urllib.error.HTTPError(url="u", code=429, msg="x", hdrs=None, fp=None)
            return "ok"

        with patch("safecode.llm.retry.time.sleep"):
            retry_call(fn, max_attempts=3, base_delay=0.0, progress_callback=stages.append)
        assert "rate_limited" in stages

    def test_failed_called_on_exhaustion(self):
        stages: list[str] = []

        def always_fail():
            raise urllib.error.URLError("always down")

        with patch("safecode.llm.retry.time.sleep"):
            with pytest.raises(urllib.error.URLError):
                retry_call(always_fail, max_attempts=2, base_delay=0.0,
                            progress_callback=stages.append)
        assert "failed" in stages

    def test_callback_exception_does_not_crash_retry(self):
        """A buggy progress_callback must not prevent the request from going through."""
        def bad_callback(stage: str) -> None:
            raise RuntimeError("callback failure")

        result = retry_call(lambda: "ok", progress_callback=bad_callback)
        assert result == "ok"


# ---------------------------------------------------------------------------
# Config knobs wired into OpenAICompatibleLLMClient
# ---------------------------------------------------------------------------


class TestClientConfigKnobs:
    def _make_config(self, **llm_overrides):
        from safecode.config import SafeCodeConfig
        cfg = SafeCodeConfig()
        cfg.sandbox.network_enabled = True
        cfg.llm.base_url = "https://api.deepseek.com"
        cfg.llm.model = "deepseek-v4-pro"
        for k, v in llm_overrides.items():
            setattr(cfg.llm, k, v)
        return cfg

    def test_request_timeout_used(self):
        import os
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = self._make_config(request_timeout_seconds=15)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client._request_timeout == 15

    def test_max_retries_used(self):
        import os
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = self._make_config(max_retries=5)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client._max_retries == 5

    def test_retry_base_delay_used(self):
        import os
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        cfg = self._make_config(retry_base_delay_seconds=2.0)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            client = OpenAICompatibleLLMClient(cfg, api_key_env="DEEPSEEK_API_KEY")
        assert client._retry_base_delay == 2.0

    def test_progress_callback_stored(self):
        import os
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        stages: list[str] = []
        cfg = self._make_config()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            client = OpenAICompatibleLLMClient(
                cfg, api_key_env="DEEPSEEK_API_KEY", progress_callback=stages.append
            )
        assert client._progress_callback is not None
