"""Bounded retry with jitter for LLM transport calls."""

from __future__ import annotations

import random
import time
import urllib.error
from email.utils import parsedate_to_datetime
from typing import Callable, TypeVar

T = TypeVar("T")

_RETRYABLE_HTTP_STATUSES = frozenset({429, 503})


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
) -> T:
    """Call fn with bounded retry on transient transport errors.

    Retries on urllib.error.URLError (connection errors) and
    urllib.error.HTTPError with status 429 or 503. Does not retry
    other 4xx or 5xx responses.

    Jitter formula: uniform(0.5, 1.5) * base_delay * 2^attempt.
    Retry-After header (if get_retry_after returns a value) replaces the
    computed delay when it is larger.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_HTTP_STATUSES:
                raise
            last_exc = exc
            reason = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            last_exc = exc
            reason = str(exc.reason)

        if attempt + 1 >= max_attempts:
            break

        computed = random.uniform(0.5, 1.5) * base_delay * (2**attempt)
        if get_retry_after is not None:
            try:
                after = get_retry_after()
                if after is not None:
                    computed = max(computed, after)
            except Exception:
                pass

        if log_fn is not None:
            log_fn(attempt + 1, reason)

        time.sleep(computed)

    assert last_exc is not None
    raise last_exc
