"""PostgreSQL backend contract suite (v2.1.3-T2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend_contract import CONTRACT_EXERCISES, BackendBundle

pytestmark = pytest.mark.postgres_integration


@pytest.fixture
def backend_bundle(postgres_backend, tmp_path: Path) -> BackendBundle:
    return BackendBundle(backend=postgres_backend, sac_root=tmp_path / ".sac")


@pytest.mark.parametrize(("exercise_name", "exercise"), CONTRACT_EXERCISES)
def test_postgres_backend_contract(backend_bundle, exercise_name: str, exercise) -> None:
    exercise(backend_bundle)
