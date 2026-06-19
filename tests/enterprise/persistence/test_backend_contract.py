"""Parametrized backend contract suite (v2.1.2-T3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend_contract import CONTRACT_EXERCISES, make_bundle
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.strict_fake import StrictFakeBackend


def _local_factory(sac_root: Path) -> LocalBackend:
    return LocalBackend(sac_root)


def _strict_fake_factory(sac_root: Path) -> StrictFakeBackend:
    return StrictFakeBackend(sac_root)


BACKEND_FACTORIES = {
    "local": _local_factory,
    "strict_fake": _strict_fake_factory,
}


@pytest.fixture(params=sorted(BACKEND_FACTORIES))
def backend_bundle(request, tmp_path: Path):
    factory = BACKEND_FACTORIES[request.param]
    return make_bundle(factory, tmp_path)


@pytest.mark.parametrize(("exercise_name", "exercise"), CONTRACT_EXERCISES)
def test_backend_contract(backend_bundle, exercise_name: str, exercise) -> None:
    exercise(backend_bundle)
