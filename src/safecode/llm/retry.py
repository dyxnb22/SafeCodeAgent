"""Bounded retry with jitter for LLM transport calls."""

from __future__ import annotations

import random
import re
import time
import urllib.error
from email.utils import parsedate_to_datetime
from typing import Callable, TypeVar

T = TypeVar("T")

_RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 502, 503, 504})

# Maximum number of seconds to honor a Retry-After header before capping it.
_MAX_RETRY_AFTER_SECONDS: float = 30.0


_URL_PATTERN = re.compile(r"https?://[^\s]+")


def _sanitize_retry_reason(reason: str) -> str:
    """Strip URLs and secrets from retry log messages (B12 fix).

    Replaces ``http://...`` / ``https://...`` with ``[URL]`` and applies
    secret redaction so internal endpoints and credentials never appear in logs.
    """
    sanitized = _URL_PATTERN.sub("[URL]", reason)
    try:
        from safecode.context.redaction import redact_secrets
        sanitized = redact_secrets(sanitized)
    except Exception:
        pass
    return sanitized


class RateLimitError(RuntimeError):
    """Raised when 429 retries are exhausted.

    Typed so callers can distinguish rate-limit exhaustion from other failures.
    The error message includes only the HTTP status code — it never includes
    caller-supplied prompts or response body content.
    """


def _parse_retry_after(header_value: str) -> float | None:
    """Parse Retry-After header: seconds (int) or HTTP-date string."""
    try:
        return float(header_value.strip())
    except (ValueError, AttributeError):
        pass
    try:
        dt = parsedate_to_datetime(header_value.strip())
        delay = (dt - dt.now(tz=dt.tzinfo)).total_seconds()
        return max(0.0, delay)
    except Exception:
        return None


def retry_call(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    get_retry_after: Callable[[], float | None] | None = None,
    log_fn: Callable[[int, str], None] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> T:
    """Call fn with bounded retry on transient transport errors.

    Retries on urllib.error.URLError (connection errors) and
    urllib.error.HTTPError with statuses 408, 429, 502, 503, 504.
    Does not retry other 4xx or 5xx responses.

    Retry-After header values are honored but capped at _MAX_RETRY_AFTER_SECONDS.
    When 429 retries are exhausted, RateLimitError is raised instead of the raw
    HTTPError so callers can distinguish rate-limit exhaustion.

    Jitter formula: uniform(0.5, 1.5) * base_delay * 2^attempt.
    Retry-After header (if get_retry_after returns a value) replaces the
    computed delay when it is larger, capped at _MAX_RETRY_AFTER_SECONDS.

    progress_callback, when provided, is called with stage strings:
      "request_started", "retrying", "rate_limited", "response_received",
      "parsed", "failed". Never raises; errors in the callback are swallowed.
    """
    def _cb(stage: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(stage)
            except Exception:
                pass

    last_exc: Exception | None = None
    last_was_rate_limit = False
    _cb("request_started")
    for attempt in range(max_attempts):
        try:
            result = fn()
            _cb("response_received")
            return result
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_HTTP_STATUSES:
                _cb("failed")
                raise
            last_was_rate_limit = exc.code == 429
            last_exc = exc
            reason = f"HTTP {exc.code}"
            if last_was_rate_limit:
                _cb("rate_limited")
            else:
                _cb("retrying")
        except urllib.error.URLError as exc:
            last_exc = exc
            last_was_rate_limit = False
            reason = str(exc.reason)
            _cb("retrying")

        if attempt + 1 >= max_attempts:
            break

        computed = random.uniform(0.5, 1.5) * base_delay * (2**attempt)
        if get_retry_after is not None:
            try:
                after = get_retry_after()
                if after is not None:
                    # Cap Retry-After to prevent server-driven DoS.
                    capped = min(after, _MAX_RETRY_AFTER_SECONDS)
                    computed = max(computed, capped)
            except Exception:
                pass

        if log_fn is not None:
            log_fn(attempt + 1, _sanitize_retry_reason(reason))

        time.sleep(computed)

    _cb("failed")
    assert last_exc is not None
    if last_was_rate_limit:
        raise RateLimitError(
            f"LLM provider rate limit (429) exhausted after {max_attempts} attempts."
        ) from last_exc
    raise last_exc
