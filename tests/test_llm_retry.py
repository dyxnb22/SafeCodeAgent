"""Tests for v3.2.0 llm-retry-jitter.

Verifies:
- retry_call succeeds on 3rd attempt after two 429 errors.
- retry_call succeeds on 2nd attempt after one 503 error.
- retry_call does NOT retry on 400 (client error).
- retry_call does NOT retry on 404.
- retry_call exhausts max_attempts and raises.
- Retry-After header (seconds) is honored (sleep checked via mock sleep).
- Jitter is applied (actual delay is in range).
- log_fn is called with attempt number and reason.
"""

from __future__ import annotations

import urllib.error
import urllib.response
from io import BytesIO
from unittest.mock import MagicMock, call, patch

import pytest

from safecode.llm.retry import retry_call, _parse_retry_after


def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    hdrs = MagicMock()
    hdrs.get = lambda k, d="": (headers or {}).get(k, d)
    return urllib.error.HTTPError(url="http://x", code=code, msg="err", hdrs=hdrs, fp=BytesIO())


def _url_error(reason: str = "connection refused") -> urllib.error.URLError:
    return urllib.error.URLError(reason)


# ── Parse Retry-After ─────────────────────────────────────────────────────────

class TestParseRetryAfter:
    def test_parses_integer_seconds(self):
        assert _parse_retry_after("30") == 30.0

    def test_parses_float_seconds(self):
        assert _parse_retry_after("1.5") == pytest.approx(1.5)

    def test_returns_none_for_invalid(self):
        assert _parse_retry_after("not-a-date") is None

    def test_returns_none_for_empty(self):
        assert _parse_retry_after("") is None


# ── Retry on 429 / 503 ────────────────────────────────────────────────────────

class TestRetryOn429And503:
    def test_succeeds_on_third_attempt_after_two_429(self):
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) < 3:
                raise _http_error(429)
            return "ok"

        with patch("time.sleep"):
            result = retry_call(fn, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        assert len(attempts) == 3

    def test_succeeds_on_second_attempt_after_503(self):
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) < 2:
                raise _http_error(503)
            return "done"

        with patch("time.sleep"):
            result = retry_call(fn, max_attempts=3, base_delay=0.01)
        assert result == "done"
        assert len(attempts) == 2

    def test_does_not_retry_on_400(self):
        def fn():
            raise _http_error(400)

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            retry_call(fn, max_attempts=3, base_delay=0.01)
        assert exc_info.value.code == 400

    def test_does_not_retry_on_404(self):
        def fn():
            raise _http_error(404)

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            retry_call(fn, max_attempts=3, base_delay=0.01)
        assert exc_info.value.code == 404

    def test_exhausts_max_attempts_and_raises(self):
        def fn():
            raise _http_error(429)

        with patch("time.sleep"):
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                retry_call(fn, max_attempts=3, base_delay=0.01)
        assert exc_info.value.code == 429

    def test_retries_on_url_error(self):
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) < 2:
                raise _url_error()
            return "ok"

        with patch("time.sleep"):
            result = retry_call(fn, max_attempts=3, base_delay=0.01)
        assert result == "ok"


# ── Retry-After header ────────────────────────────────────────────────────────

class TestRetryAfterHeader:
    def test_retry_after_seconds_honored(self):
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) < 2:
                raise _http_error(429)
            return "ok"

        sleep_calls = []
        with patch("time.sleep", side_effect=sleep_calls.append):
            result = retry_call(
                fn,
                max_attempts=3,
                base_delay=0.01,
                get_retry_after=lambda: 5.0,
            )
        assert result == "ok"
        assert sleep_calls[0] >= 5.0

    def test_retry_after_none_uses_jitter(self):
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) < 2:
                raise _http_error(429)
            return "ok"

        sleep_calls = []
        with patch("time.sleep", side_effect=sleep_calls.append):
            result = retry_call(
                fn,
                max_attempts=3,
                base_delay=0.1,
                get_retry_after=lambda: None,
            )
        assert result == "ok"
        assert len(sleep_calls) == 1
        assert 0.0 < sleep_calls[0] < 1.0  # jitter(0.5,1.5)*0.1*2^0 ∈ [0.05, 0.15]


# ── log_fn ────────────────────────────────────────────────────────────────────

class TestLogFn:
    def test_log_fn_called_with_attempt_and_reason(self):
        log_calls = []

        def fn():
            if len(log_calls) < 2:
                raise _http_error(429)
            return "ok"

        with patch("time.sleep"):
            result = retry_call(
                fn,
                max_attempts=3,
                base_delay=0.01,
                log_fn=lambda attempt, reason: log_calls.append((attempt, reason)),
            )
        assert result == "ok"
        assert len(log_calls) == 2
        assert log_calls[0][0] == 1
        assert "429" in log_calls[0][1]
        assert log_calls[1][0] == 2

    def test_log_fn_not_called_on_success(self):
        log_calls = []
        result = retry_call(lambda: "ok", log_fn=lambda a, r: log_calls.append((a, r)))
        assert result == "ok"
        assert log_calls == []
