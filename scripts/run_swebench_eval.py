#!/usr/bin/env python3
"""Run SWE-bench-inspired harder eval fixtures against DeepSeek and write snapshot.

These fixtures are modelled on real bug patterns found in SWE-bench Lite
(sympy, requests, django, flask, numpy, etc.) but are self-contained inline
projects that don't require checking out external repos.

Usage:
    DEEPSEEK_API_KEY=sk-... python scripts/run_swebench_eval.py
    python scripts/run_swebench_eval.py sk-...   # key as CLI arg
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from safecode.eval.live import LiveEvalFixture, LiveEvalRunner


# ---------------------------------------------------------------------------
# SWE-bench-inspired hard fixtures
# ---------------------------------------------------------------------------

def _swe_mutable_default_arg() -> LiveEvalFixture:
    """Classic mutable default argument bug — found in many real Python projects."""
    code = '''\
def accumulate(value, cache=[]):
    """Accumulate values across calls."""
    cache.append(value)
    return list(cache)


def process_batch(items, result={}):
    """Process items and return per-key results."""
    for item in items:
        result[item["key"]] = item["value"] * 2
    return dict(result)
'''
    tests = '''\
from src.collector import accumulate, process_batch


def test_accumulate_independent_calls():
    r1 = accumulate(1)
    r2 = accumulate(2)
    # Each call with no explicit cache should start fresh — but the bug
    # causes cache to persist across calls.
    assert r1 == [1], f"expected [1], got {r1}"
    assert r2 == [2], f"expected [2], got {r2}"


def test_process_batch_independent():
    b1 = process_batch([{"key": "a", "value": 1}])
    b2 = process_batch([{"key": "b", "value": 2}])
    assert b1 == {"a": 2}, f"got {b1}"
    assert b2 == {"b": 4}, f"got {b2}"
'''
    def success(root: Path) -> bool:
        src = root / "src" / "collector.py"
        if not src.exists():
            return False
        text = src.read_text()
        # Must not use mutable defaults
        if "cache=[]" in text or "result={}" in text:
            return False
        # Run pytest
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_collector.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-mutable-default-arg",
        setup_files={"src/__init__.py": "", "src/collector.py": code, "tests/test_collector.py": tests},
        goal=(
            "src/collector.py has two functions with mutable default arguments — a classic Python bug "
            "where the default list/dict is shared across all calls. "
            "Fix both accumulate() and process_batch() so each call with no explicit argument "
            "starts with an empty collection. tests/test_collector.py must pass."
        ),
        success_condition=success,
        max_turns=8,
        category="bug-fix",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_collector.py -q"],
    )


def _swe_generator_exhaustion() -> LiveEvalFixture:
    """Generator exhaustion bug — iterator consumed once, silently returns empty."""
    code = '''\
def find_evens(numbers):
    """Return a list of even numbers from the input."""
    gen = (n for n in numbers if n % 2 == 0)
    if not any(gen):        # BUG: exhausts the generator
        return []
    return list(gen)        # always returns [] because gen is already exhausted


def count_and_collect(items, predicate):
    """Return (count, items) matching predicate."""
    filtered = filter(predicate, items)
    count = sum(1 for _ in filtered)   # BUG: exhausts the filter iterator
    return count, list(filtered)       # always returns (N, [])
'''
    tests = '''\
from src.itertools_utils import find_evens, count_and_collect


def test_find_evens_basic():
    assert find_evens([1, 2, 3, 4, 5]) == [2, 4]


def test_find_evens_all_odd():
    assert find_evens([1, 3, 5]) == []


def test_find_evens_all_even():
    assert find_evens([2, 4, 6]) == [2, 4, 6]


def test_count_and_collect():
    count, items = count_and_collect([1, 2, 3, 4], lambda x: x > 2)
    assert count == 2, f"count={count}"
    assert sorted(items) == [3, 4], f"items={items}"
'''
    def success(root: Path) -> bool:
        src = root / "src" / "itertools_utils.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_itertools.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-generator-exhaustion",
        setup_files={
            "src/__init__.py": "",
            "src/itertools_utils.py": code,
            "tests/test_itertools.py": tests,
        },
        goal=(
            "src/itertools_utils.py has two functions with iterator/generator exhaustion bugs. "
            "find_evens() consumes the generator with any() then tries to iterate it again (always empty). "
            "count_and_collect() exhausts the filter with sum() then tries to collect (always empty). "
            "Fix both functions so the tests in tests/test_itertools.py pass."
        ),
        success_condition=success,
        max_turns=8,
        category="bug-fix",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_itertools.py -q"],
    )


def _swe_integer_division() -> LiveEvalFixture:
    """Integer vs float division — common in porting Python 2 to 3 and in stats code."""
    code = '''\
def mean(values):
    """Return the arithmetic mean of a sequence of numbers."""
    if not values:
        raise ValueError("mean of empty sequence")
    return sum(values) // len(values)   # BUG: integer division truncates


def weighted_average(items):
    """Return weighted average. items = [(value, weight), ...]"""
    if not items:
        raise ValueError("empty items")
    total_weight = sum(w for _, w in items)
    total_value = sum(v * w for v, w in items)
    return total_value // total_weight   # BUG: integer division
'''
    tests = '''\
from src.stats import mean, weighted_average


def test_mean_integers():
    assert mean([1, 2]) == 1.5


def test_mean_single():
    assert mean([7]) == 7.0


def test_mean_mixed():
    assert abs(mean([1, 2, 3]) - 2.0) < 1e-9


def test_mean_empty():
    import pytest
    with pytest.raises(ValueError):
        mean([])


def test_weighted_average():
    # (10, weight=1), (20, weight=3)  =>  (10*1 + 20*3) / (1+3) = 70/4 = 17.5
    assert weighted_average([(10, 1), (20, 3)]) == 17.5


def test_weighted_average_equal_weights():
    assert weighted_average([(5, 1), (15, 1)]) == 10.0
'''
    def success(root: Path) -> bool:
        src = root / "src" / "stats.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_stats.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-integer-division",
        setup_files={
            "src/__init__.py": "",
            "src/stats.py": code,
            "tests/test_stats.py": tests,
        },
        goal=(
            "src/stats.py uses integer division (//) in mean() and weighted_average(), "
            "causing incorrect results for non-integer averages (e.g. mean([1,2]) returns 1 instead of 1.5). "
            "Fix both functions to use float division. tests/test_stats.py must pass."
        ),
        success_condition=success,
        max_turns=6,
        category="bug-fix",
        expected_difficulty="easy",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_stats.py -q"],
    )


def _swe_exception_swallow() -> LiveEvalFixture:
    """Silent exception swallowing — hides errors from callers."""
    code = '''\
import json


def parse_config(path):
    """Parse a JSON config file. Returns dict or raises on invalid JSON."""
    try:
        with open(path) as f:
            return json.load(f)
    except:          # BUG: catches ALL exceptions including KeyboardInterrupt
        return {}    # silently returns empty dict on any error


def load_plugin(module_name):
    """Import and return a plugin module."""
    try:
        import importlib
        return importlib.import_module(module_name)
    except ImportError:
        return None
    except:          # BUG: swallows unexpected errors like SyntaxError
        return None
'''
    tests = '''\
import pytest
import json
import os
from pathlib import Path
from src.loader import parse_config, load_plugin


def test_parse_config_invalid_json(tmp_path):
    bad_file = tmp_path / "config.json"
    bad_file.write_text("{ not valid json }")
    # Should raise json.JSONDecodeError (or ValueError), not return {}
    with pytest.raises((json.JSONDecodeError, ValueError)):
        parse_config(str(bad_file))


def test_parse_config_file_not_found(tmp_path):
    missing = str(tmp_path / "nonexistent.json")
    # Should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        parse_config(missing)


def test_parse_config_valid(tmp_path):
    good_file = tmp_path / "config.json"
    good_file.write_text(\'{"key": "value"}\')
    result = parse_config(str(good_file))
    assert result == {"key": "value"}


def test_load_plugin_missing():
    result = load_plugin("nonexistent_module_xyz_123")
    assert result is None


def test_load_plugin_syntax_error(tmp_path, monkeypatch):
    # SyntaxError in a module should propagate, not be silently swallowed.
    plugin_dir = tmp_path / "bad_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("def foo( :  # syntax error")
    import sys
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(SyntaxError):
        load_plugin("bad_plugin")
'''
    def success(root: Path) -> bool:
        src = root / "src" / "loader.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_loader.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-exception-swallow",
        setup_files={
            "src/__init__.py": "",
            "src/loader.py": code,
            "tests/test_loader.py": tests,
        },
        goal=(
            "src/loader.py has two functions that use bare except: clauses and silently return "
            "empty values on any error. parse_config() should raise json.JSONDecodeError on invalid "
            "JSON and FileNotFoundError on missing file. load_plugin() should still return None for "
            "ImportError but let SyntaxError propagate. Fix both functions so tests/test_loader.py passes."
        ),
        success_condition=success,
        max_turns=8,
        category="bug-fix",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_loader.py -q"],
    )


def _swe_decorator_signature() -> LiveEvalFixture:
    """Missing functools.wraps — loses function metadata, breaks help() and type checkers."""
    code = '''\
import time


def retry(max_attempts=3, delay=0.0):
    """Retry decorator — retries on RuntimeError up to max_attempts times."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except RuntimeError as e:
                    last_exc = e
                    if delay > 0:
                        time.sleep(delay)
            raise last_exc
        return wrapper    # BUG: wrapper has wrong __name__, __doc__, __wrapped__
    return decorator


def cache_result(func):
    """Simple in-memory memoisation decorator."""
    _cache = {}
    def cached(*args):
        if args not in _cache:
            _cache[args] = func(*args)
        return _cache[args]
    return cached    # BUG: cached has wrong __name__, __doc__
'''
    tests = '''\
import functools
from src.decorators import retry, cache_result


def test_retry_preserves_name():
    @retry(max_attempts=2)
    def my_function():
        """My docstring."""
        pass
    assert my_function.__name__ == "my_function", f"got {my_function.__name__}"


def test_retry_preserves_doc():
    @retry()
    def documented():
        """Important docs."""
        pass
    assert documented.__doc__ == "Important docs.", f"got {documented.__doc__!r}"


def test_retry_works():
    attempts = []
    @retry(max_attempts=3, delay=0)
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("not yet")
        return "ok"
    assert flaky() == "ok"
    assert len(attempts) == 3


def test_cache_preserves_name():
    @cache_result
    def compute(x):
        """Compute something."""
        return x * 2
    assert compute.__name__ == "compute", f"got {compute.__name__}"


def test_cache_preserves_doc():
    @cache_result
    def compute(x):
        """Compute something."""
        return x * 2
    assert compute.__doc__ == "Compute something.", f"got {compute.__doc__!r}"


def test_cache_works():
    calls = []
    @cache_result
    def expensive(n):
        calls.append(n)
        return n ** 2
    assert expensive(4) == 16
    assert expensive(4) == 16
    assert len(calls) == 1   # only called once
'''
    def success(root: Path) -> bool:
        src = root / "src" / "decorators.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_decorators.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-decorator-signature",
        setup_files={
            "src/__init__.py": "",
            "src/decorators.py": code,
            "tests/test_decorators.py": tests,
        },
        goal=(
            "src/decorators.py has two decorators (retry and cache_result) whose inner wrapper "
            "functions do not use functools.wraps, causing them to lose the wrapped function's "
            "__name__ and __doc__. Fix both decorators to preserve function metadata. "
            "tests/test_decorators.py must pass."
        ),
        success_condition=success,
        max_turns=8,
        category="refactor",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_decorators.py -q"],
    )


def _swe_json_serialization() -> LiveEvalFixture:
    """JSON serialization failing on non-standard Python types — common in API/data code."""
    code = '''\
import json
from datetime import date, datetime
from decimal import Decimal


def to_json(data):
    """Serialise data to a JSON string. Handles standard types only."""
    return json.dumps(data)    # BUG: fails on date, datetime, Decimal


def from_json(text):
    """Deserialise a JSON string."""
    return json.loads(text)
'''
    tests = '''\
import json
from datetime import date, datetime
from decimal import Decimal
from src.serializer import to_json, from_json


def test_to_json_basic():
    assert to_json({"key": "value"}) == \'{"key": "value"}\'


def test_to_json_date():
    result = to_json({"date": date(2024, 1, 15)})
    parsed = json.loads(result)
    assert parsed["date"] == "2024-01-15"


def test_to_json_datetime():
    result = to_json({"ts": datetime(2024, 1, 15, 12, 30, 0)})
    parsed = json.loads(result)
    assert "2024-01-15" in parsed["ts"]


def test_to_json_decimal():
    result = to_json({"price": Decimal("19.99")})
    parsed = json.loads(result)
    assert abs(parsed["price"] - 19.99) < 0.001


def test_to_json_nested():
    data = {
        "name": "order",
        "date": date(2024, 6, 1),
        "total": Decimal("42.00"),
    }
    result = to_json(data)
    parsed = json.loads(result)
    assert parsed["name"] == "order"
    assert parsed["date"] == "2024-06-01"


def test_from_json_roundtrip():
    original = \'{"a": 1, "b": "hello"}\'
    assert from_json(original) == {"a": 1, "b": "hello"}
'''
    def success(root: Path) -> bool:
        src = root / "src" / "serializer.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_serializer.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-json-serialization",
        setup_files={
            "src/__init__.py": "",
            "src/serializer.py": code,
            "tests/test_serializer.py": tests,
        },
        goal=(
            "src/serializer.py has a to_json() function that calls json.dumps() without a custom "
            "encoder, causing TypeError when the data contains datetime.date, datetime.datetime, "
            "or decimal.Decimal values. Fix to_json() to handle these types gracefully "
            "(dates as ISO strings, Decimal as float). tests/test_serializer.py must pass."
        ),
        success_condition=success,
        max_turns=8,
        category="bug-fix",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_serializer.py -q"],
    )


def _swe_off_by_one_slice() -> LiveEvalFixture:
    """Off-by-one in slice / range — extremely common bug type in SWE-bench."""
    code = '''\
def sliding_window(sequence, size):
    """Return all contiguous sub-sequences of the given size."""
    if size <= 0 or size > len(sequence):
        return []
    result = []
    for i in range(len(sequence) - size):   # BUG: misses the last window
        result.append(sequence[i:i + size])
    return result


def paginate(items, page_size, page_number):
    """Return a page of items. page_number is 1-indexed."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    start = (page_number - 1) * page_size
    end = start + page_size - 1    # BUG: should be start + page_size (exclusive end)
    return items[start:end]
'''
    tests = '''\
from src.slicing import sliding_window, paginate


def test_sliding_window_basic():
    result = sliding_window([1, 2, 3, 4, 5], 3)
    assert result == [[1, 2, 3], [2, 3, 4], [3, 4, 5]], f"got {result}"


def test_sliding_window_size_equals_length():
    assert sliding_window([1, 2, 3], 3) == [[1, 2, 3]]


def test_sliding_window_size_1():
    assert sliding_window([10, 20, 30], 1) == [[10], [20], [30]]


def test_sliding_window_too_big():
    assert sliding_window([1, 2], 5) == []


def test_paginate_first_page():
    items = list(range(10))
    result = paginate(items, page_size=3, page_number=1)
    assert result == [0, 1, 2], f"got {result}"


def test_paginate_second_page():
    items = list(range(10))
    result = paginate(items, page_size=3, page_number=2)
    assert result == [3, 4, 5], f"got {result}"


def test_paginate_last_page():
    items = list(range(7))
    result = paginate(items, page_size=3, page_number=3)
    assert result == [6], f"got {result}"
'''
    def success(root: Path) -> bool:
        src = root / "src" / "slicing.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_slicing.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-off-by-one-slice",
        setup_files={
            "src/__init__.py": "",
            "src/slicing.py": code,
            "tests/test_slicing.py": tests,
        },
        goal=(
            "src/slicing.py has two off-by-one bugs: "
            "sliding_window() uses range(len(sequence) - size) which misses the last window "
            "(should be range(len(sequence) - size + 1)); "
            "paginate() uses end = start + page_size - 1 as a slice end (should be start + page_size). "
            "Fix both. tests/test_slicing.py must pass."
        ),
        success_condition=success,
        max_turns=6,
        category="bug-fix",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_slicing.py -q"],
    )


def _swe_multifile_api_version() -> LiveEvalFixture:
    """Multi-file: add API version header to a request client used across modules."""
    client_code = '''\
import urllib.request
import json


class APIClient:
    """Simple HTTP client for the example API."""

    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get(self, path):
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def post(self, path, data):
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
'''
    models_code = '''\
from .client import APIClient


class UserAPI:
    def __init__(self, client: APIClient):
        self.client = client

    def get_user(self, user_id):
        return self.client.get(f"/users/{user_id}")


class OrderAPI:
    def __init__(self, client: APIClient):
        self.client = client

    def create_order(self, items):
        return self.client.post("/orders", {"items": items})
'''
    tests = '''\
from unittest.mock import patch, MagicMock
from sdk.client import APIClient
from sdk.models import UserAPI, OrderAPI


def _make_client():
    return APIClient("https://api.example.com", "test-key")


def _headers_from_client(client):
    return client._headers()


def test_api_version_header_present():
    client = _make_client()
    headers = _headers_from_client(client)
    assert "X-API-Version" in headers, f"Missing X-API-Version in {list(headers)}"


def test_api_version_value():
    client = _make_client()
    headers = _headers_from_client(client)
    assert headers["X-API-Version"] == "2024-01", (
        f"Expected \'2024-01\', got {headers.get(\'X-API-Version\')!r}"
    )


def test_auth_header_still_present():
    client = _make_client()
    headers = _headers_from_client(client)
    assert "Authorization" in headers


def test_user_api_uses_client(monkeypatch):
    client = _make_client()
    mock_get = MagicMock(return_value={"id": 42})
    monkeypatch.setattr(client, "get", mock_get)
    api = UserAPI(client)
    result = api.get_user(42)
    mock_get.assert_called_once_with("/users/42")
    assert result == {"id": 42}


def test_order_api_uses_client(monkeypatch):
    client = _make_client()
    mock_post = MagicMock(return_value={"order_id": 1})
    monkeypatch.setattr(client, "post", mock_post)
    api = OrderAPI(client)
    result = api.create_order(["item1"])
    mock_post.assert_called_once_with("/orders", {"items": ["item1"]})
'''
    def success(root: Path) -> bool:
        src = root / "sdk" / "client.py"
        if not src.exists():
            return False
        text = src.read_text()
        if "X-API-Version" not in text:
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_sdk.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-multifile-api-version",
        setup_files={
            "sdk/__init__.py": "",
            "sdk/client.py": client_code,
            "sdk/models.py": models_code,
            "tests/__init__.py": "",
            "tests/test_sdk.py": tests,
        },
        goal=(
            "The SDK's APIClient._headers() method is missing the required 'X-API-Version: 2024-01' header. "
            "Add it to _headers() in sdk/client.py. All existing headers (Authorization, Content-Type) "
            "must remain. tests/test_sdk.py must pass."
        ),
        success_condition=success,
        max_turns=6,
        category="bug-fix",
        expected_difficulty="easy",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_sdk.py -q"],
    )


def _swe_string_format_bug() -> LiveEvalFixture:
    """Incorrect format string — wrong variable used in output."""
    code = '''\
def format_error(code, message, context=None):
    """Format a structured error message."""
    if context:
        return f"[{code}] Error: {message} (in {message})"   # BUG: 'message' used twice, should be 'context'
    return f"[{code}] Error: {message}"


def build_sql_in_clause(column, values):
    """Build a SQL IN clause string (parameterised)."""
    if not values:
        return "1=0"
    placeholders = ", ".join(["%s"] * len(values))
    return f"{column} NOT IN ({placeholders})"   # BUG: should be IN, not NOT IN
'''
    tests = '''\
from src.formatting import format_error, build_sql_in_clause


def test_format_error_with_context():
    result = format_error("E404", "not found", context="user_service")
    assert "user_service" in result, f"context missing from: {result!r}"
    assert result.count("not found") == 1, f"message duplicated in: {result!r}"


def test_format_error_without_context():
    result = format_error("E500", "internal error")
    assert result == "[E500] Error: internal error"


def test_format_error_context_not_duplicated():
    result = format_error("E403", "forbidden", context="admin_api")
    # 'forbidden' should appear exactly once, 'admin_api' should appear once
    assert result.count("forbidden") == 1
    assert result.count("admin_api") == 1


def test_sql_in_clause_basic():
    result = build_sql_in_clause("status", ["active", "pending"])
    assert "NOT IN" not in result, f"should be IN, not NOT IN: {result!r}"
    assert "IN" in result


def test_sql_in_clause_single():
    result = build_sql_in_clause("id", [42])
    assert result == "id IN (%s)", f"got {result!r}"


def test_sql_in_clause_empty():
    result = build_sql_in_clause("id", [])
    assert result == "1=0"
'''
    def success(root: Path) -> bool:
        src = root / "src" / "formatting.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_formatting.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-string-format-bug",
        setup_files={
            "src/__init__.py": "",
            "src/formatting.py": code,
            "tests/test_formatting.py": tests,
        },
        goal=(
            "src/formatting.py has two bugs: "
            "format_error() uses {message} twice in the context branch (should use {context}); "
            "build_sql_in_clause() generates NOT IN instead of IN. "
            "Fix both. tests/test_formatting.py must pass."
        ),
        success_condition=success,
        max_turns=6,
        category="bug-fix",
        expected_difficulty="easy",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_formatting.py -q"],
    )


def _swe_context_manager_exit() -> LiveEvalFixture:
    """Context manager __exit__ doesn't suppress exceptions correctly."""
    code = '''\
class SuppressErrors:
    """Context manager that suppresses specified exception types."""

    def __init__(self, *exception_types):
        self.exception_types = exception_types
        self.exception = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and issubclass(exc_type, self.exception_types):
            self.exception = exc_val
            return   # BUG: returns None (falsy), doesn't suppress the exception


class Timer:
    """Context manager that measures elapsed time."""
    import time as _time

    def __enter__(self):
        self._start = self._time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = self._time.perf_counter() - self._start
        # BUG: missing return False — implicit None return is fine here but
        # should be explicit to clarify intent and satisfy type checkers
        # ACTUALLY this one is correct, keep it. Only SuppressErrors is broken.


class AtomicWriter:
    """Write to a temp file then rename atomically; rollback on exception."""
    import os as _os

    def __init__(self, path):
        self.path = path
        self._tmp = path + ".tmp"
        self._file = None

    def __enter__(self):
        self._file = open(self._tmp, "w")
        return self._file

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._file.close()
        if exc_type is None:
            self._os.replace(self._tmp, self.path)
        else:
            self._os.unlink(self._tmp)
        # BUG: should return False (or not return True) to let exceptions propagate
        return True   # BUG: silently swallows all exceptions
'''
    tests = '''\
import pytest
from src.context_managers import SuppressErrors, AtomicWriter
from pathlib import Path


def test_suppress_errors_suppresses_target():
    with SuppressErrors(ValueError):
        raise ValueError("ok")
    # Should reach here without exception


def test_suppress_errors_stores_exception():
    with SuppressErrors(ValueError) as ctx:
        raise ValueError("stored")
    assert isinstance(ctx.exception, ValueError)
    assert str(ctx.exception) == "stored"


def test_suppress_errors_lets_other_exceptions_through():
    with pytest.raises(TypeError):
        with SuppressErrors(ValueError):
            raise TypeError("should propagate")


def test_suppress_errors_no_exception():
    with SuppressErrors(ValueError) as ctx:
        pass
    assert ctx.exception is None


def test_atomic_writer_success(tmp_path):
    target = tmp_path / "output.txt"
    with AtomicWriter(str(target)) as f:
        f.write("hello")
    assert target.read_text() == "hello"
    assert not (tmp_path / "output.txt.tmp").exists()


def test_atomic_writer_rollback_on_exception(tmp_path):
    target = tmp_path / "output.txt"
    with pytest.raises(RuntimeError):
        with AtomicWriter(str(target)) as f:
            f.write("partial")
            raise RuntimeError("write failed")
    # Target should NOT exist (rollback), temp should be cleaned up
    assert not target.exists()
    assert not (tmp_path / "output.txt.tmp").exists()
'''
    def success(root: Path) -> bool:
        src = root / "src" / "context_managers.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_context_managers.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-context-manager-exit",
        setup_files={
            "src/__init__.py": "",
            "src/context_managers.py": code,
            "tests/test_context_managers.py": tests,
        },
        goal=(
            "src/context_managers.py has two context manager bugs: "
            "SuppressErrors.__exit__() returns None (not True) when suppressing an exception, "
            "so the exception propagates anyway — fix it to return True for suppressed exceptions. "
            "AtomicWriter.__exit__() returns True unconditionally, swallowing all exceptions — "
            "fix it to only suppress nothing (let exceptions propagate after cleanup). "
            "tests/test_context_managers.py must pass."
        ),
        success_condition=success,
        max_turns=8,
        category="bug-fix",
        expected_difficulty="hard",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_context_managers.py -q"],
    )


def _swe_dict_update_mutation() -> LiveEvalFixture:
    """Dict update mutates caller's dict — common source of data corruption bugs."""
    code = '''\
_DEFAULTS = {
    "timeout": 30,
    "retries": 3,
    "verbose": False,
    "encoding": "utf-8",
}


def get_config(overrides=None):
    """Return configuration with user overrides applied."""
    config = _DEFAULTS
    if overrides:
        config.update(overrides)   # BUG: mutates _DEFAULTS directly
    return config


def merge_settings(*settings_dicts):
    """Merge multiple settings dicts, later dicts override earlier ones."""
    result = settings_dicts[0] if settings_dicts else {}
    for d in settings_dicts[1:]:
        result.update(d)   # BUG: mutates the first dict
    return result
'''
    tests = '''\
from src.config import get_config, merge_settings, _DEFAULTS


def test_get_config_does_not_mutate_defaults():
    before = dict(_DEFAULTS)
    get_config({"timeout": 60})
    assert dict(_DEFAULTS) == before, f"_DEFAULTS was mutated: {_DEFAULTS}"


def test_get_config_applies_overrides():
    config = get_config({"timeout": 60})
    assert config["timeout"] == 60
    assert config["retries"] == 3   # default preserved


def test_get_config_no_overrides():
    config = get_config()
    assert config["timeout"] == 30


def test_get_config_repeated_calls_independent():
    c1 = get_config({"verbose": True})
    c2 = get_config()
    assert c1["verbose"] is True
    assert c2["verbose"] is False   # default restored


def test_merge_settings_does_not_mutate_first():
    d1 = {"a": 1, "b": 2}
    d1_copy = dict(d1)
    merge_settings(d1, {"b": 99, "c": 3})
    assert d1 == d1_copy, f"first dict was mutated: {d1}"


def test_merge_settings_basic():
    result = merge_settings({"a": 1}, {"b": 2}, {"a": 99})
    assert result == {"a": 99, "b": 2}


def test_merge_settings_empty():
    result = merge_settings({}, {"x": 1})
    assert result == {"x": 1}
'''
    def success(root: Path) -> bool:
        src = root / "src" / "config.py"
        if not src.exists():
            return False
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_config.py", "-q", "--tb=short"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0

    return LiveEvalFixture(
        name="swe-dict-update-mutation",
        setup_files={
            "src/__init__.py": "",
            "src/config.py": code,
            "tests/test_config.py": tests,
        },
        goal=(
            "src/config.py has two dict mutation bugs: "
            "get_config() assigns config = _DEFAULTS (not a copy) then calls config.update(), "
            "which mutates the module-level _DEFAULTS dict. "
            "merge_settings() mutates the first argument dict by calling result.update() in-place. "
            "Fix both functions so they don't mutate their inputs. tests/test_config.py must pass."
        ),
        success_condition=success,
        max_turns=6,
        category="bug-fix",
        expected_difficulty="medium",
        fixture_stability="stable",
        validation_commands=["python -m pytest tests/test_config.py -q"],
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def swe_fixtures() -> list[LiveEvalFixture]:
    return [
        _swe_mutable_default_arg(),
        _swe_generator_exhaustion(),
        _swe_integer_division(),
        _swe_exception_swallow(),
        _swe_decorator_signature(),
        _swe_json_serialization(),
        _swe_off_by_one_slice(),
        _swe_multifile_api_version(),
        _swe_string_format_bug(),
        _swe_context_manager_exit(),
        _swe_dict_update_mutation(),
    ]


def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key and len(sys.argv) > 1:
        api_key = sys.argv[1]
    if not api_key:
        print("ERROR: set DEEPSEEK_API_KEY or pass key as first argument", file=sys.stderr)
        sys.exit(1)

    os.environ["DEEPSEEK_API_KEY"] = api_key
    os.environ["SAFECODE_LIVE_TESTS"] = "1"

    fixtures = swe_fixtures()
    runner = LiveEvalRunner(provider="deepseek", model="deepseek-chat")

    print(f"Running {len(fixtures)} SWE-bench-inspired fixtures against deepseek-chat ...\n")

    results = []
    t0 = time.perf_counter()
    for fixture in fixtures:
        print(f"  [{fixture.name}] ...", end="", flush=True)
        try:
            result = runner.run_fixture(fixture)
        except Exception as exc:
            print(f" ERROR: {exc}")
            continue
        status = "PASS" if result.success else "FAIL"
        err_msg = f" — {result.error[:80]}" if result.error else ""
        print(f" {status}  ({result.turns_used} turns, {result.input_tokens + result.output_tokens} tok){err_msg}")
        results.append(result)

    elapsed = time.perf_counter() - t0
    passed = sum(1 for r in results if r.success)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"SWE-bench-inspired Results: {passed}/{total} passed ({passed/total*100:.1f}%)  [{elapsed:.1f}s]")
    print(f"{'='*60}\n")
    print(f"{'Fixture':<40} {'Status':<6} {'Turns':>5} {'Tokens':>7}")
    print("-" * 62)
    for r in results:
        s = "PASS" if r.success else "FAIL"
        print(f"{r.fixture_name:<40} {s:<6} {r.turns_used:>5} {r.input_tokens + r.output_tokens:>7}")

    # Build snapshot
    snapshot = {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "date": date.today().isoformat(),
        "suite": "swebench-inspired",
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "passed": passed,
        "total": total,
        "elapsed_seconds": round(elapsed, 1),
        "fixtures": [
            {
                "name": r.fixture_name,
                "category": r.failure_category or ("pass" if r.success else "fail"),
                "success": r.success,
                "turns_used": r.turns_used,
                "tool_calls": r.tool_calls,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "wall_seconds": round(r.wall_seconds, 2),
                "error": r.error,
            }
            for r in results
        ],
    }

    snapshot_dir = Path(__file__).parent.parent / "tests" / "snapshots" / "live_eval"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshot_dir / f"swebench-deepseek-{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nSnapshot written: {out_path}")

    # Also update latest.json with this run's results combined with existing results
    latest_path = snapshot_dir / "latest.json"
    try:
        existing = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        existing = {"results": [], "meta": {}}

    existing["meta"] = existing.get("meta", {})
    existing["meta"]["swebench_inspired"] = {
        "date": date.today().isoformat(),
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "model": "deepseek-chat",
        "provider": "deepseek",
    }
    latest_path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Updated: {latest_path}")

    sys.exit(0 if passed == total else 0)  # exit 0 regardless — partial pass is informative


if __name__ == "__main__":
    main()
