"""Tests for the golden-demo calculator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from calculator import add, multiply, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6  # fails with the buggy implementation


def test_multiply():
    assert multiply(3, 4) == 12
