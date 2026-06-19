# Enterprise test fixtures and shared helpers live here as the suite grows.

from __future__ import annotations

import sys
from pathlib import Path

_ENTERPRISE_TESTS_ROOT = Path(__file__).resolve().parent
if str(_ENTERPRISE_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_TESTS_ROOT))
