"""Live provider tests — skipped by default unless SAFECODE_LIVE_TESTS=1.

These tests make real network calls and require valid API credentials.
They are never run in normal CI or the default pytest invocation.

To opt in:
  SAFECODE_LIVE_TESTS=1 ANTHROPIC_API_KEY=sk-... python3 -m pytest tests/live/ -v
"""

import os
import pytest

_ENV_VAR = "SAFECODE_LIVE_TESTS"


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip every test in this directory unless SAFECODE_LIVE_TESTS=1."""
    if not os.getenv(_ENV_VAR):
        pytest.skip(
            f"Live provider tests are skipped by default. "
            f"Set {_ENV_VAR}=1 to run them (requires real API credentials)."
        )
