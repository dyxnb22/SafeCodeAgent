"""Tests for SandboxBackendStrategy (v2.8.2).

Proves that backend recommendation/detection can be tested independently of
CLI rendering, audit logging, and proposal execution.
"""

import pytest

from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.strategy import SandboxBackendStrategy


def _make_cap(backend: SandboxBackend, available: bool) -> SandboxCapability:
    return SandboxCapability(
        backend=backend,
        available=available,
        supported_platforms=["all"],
        reason=f"{backend.value} reason",
    )


class TestRecommendNone:
    def test_empty_capabilities_returns_none(self):
        strategy = SandboxBackendStrategy()
        assert strategy.recommend([]) == SandboxBackend.NONE

    def test_all_unavailable_returns_none(self):
        caps = [
            _make_cap(SandboxBackend.NONE, True),
            _make_cap(SandboxBackend.DOCKER, False),
            _make_cap(SandboxBackend.MACOS_SEATBELT, False),
            _make_cap(SandboxBackend.LINUX_BUBBLEWRAP, False),
        ]
        strategy = SandboxBackendStrategy()
        assert strategy.recommend(caps) == SandboxBackend.NONE

    def test_only_none_available_returns_none(self):
        caps = [_make_cap(SandboxBackend.NONE, True)]
        strategy = SandboxBackendStrategy()
        assert strategy.recommend(caps) == SandboxBackend.NONE


class TestRecommendPriority:
    def test_bubblewrap_preferred_over_seatbelt(self):
        caps = [
            _make_cap(SandboxBackend.LINUX_BUBBLEWRAP, True),
            _make_cap(SandboxBackend.MACOS_SEATBELT, True),
            _make_cap(SandboxBackend.DOCKER, True),
        ]
        assert SandboxBackendStrategy().recommend(caps) == SandboxBackend.LINUX_BUBBLEWRAP

    def test_seatbelt_preferred_over_docker(self):
        caps = [
            _make_cap(SandboxBackend.LINUX_BUBBLEWRAP, False),
            _make_cap(SandboxBackend.MACOS_SEATBELT, True),
            _make_cap(SandboxBackend.DOCKER, True),
        ]
        assert SandboxBackendStrategy().recommend(caps) == SandboxBackend.MACOS_SEATBELT

    def test_docker_preferred_over_none(self):
        caps = [
            _make_cap(SandboxBackend.LINUX_BUBBLEWRAP, False),
            _make_cap(SandboxBackend.MACOS_SEATBELT, False),
            _make_cap(SandboxBackend.DOCKER, True),
            _make_cap(SandboxBackend.NONE, True),
        ]
        assert SandboxBackendStrategy().recommend(caps) == SandboxBackend.DOCKER

    def test_bubblewrap_alone_returns_bubblewrap(self):
        caps = [_make_cap(SandboxBackend.LINUX_BUBBLEWRAP, True)]
        assert SandboxBackendStrategy().recommend(caps) == SandboxBackend.LINUX_BUBBLEWRAP

    def test_seatbelt_alone_returns_seatbelt(self):
        caps = [_make_cap(SandboxBackend.MACOS_SEATBELT, True)]
        assert SandboxBackendStrategy().recommend(caps) == SandboxBackend.MACOS_SEATBELT

    def test_docker_alone_returns_docker(self):
        caps = [_make_cap(SandboxBackend.DOCKER, True)]
        assert SandboxBackendStrategy().recommend(caps) == SandboxBackend.DOCKER


class TestAvailableBackends:
    def test_returns_available_in_priority_order(self):
        caps = [
            _make_cap(SandboxBackend.DOCKER, True),
            _make_cap(SandboxBackend.MACOS_SEATBELT, True),
            _make_cap(SandboxBackend.LINUX_BUBBLEWRAP, False),
            _make_cap(SandboxBackend.NONE, True),
        ]
        result = SandboxBackendStrategy().available_backends(caps)
        assert result == [SandboxBackend.MACOS_SEATBELT, SandboxBackend.DOCKER, SandboxBackend.NONE]

    def test_empty_returns_empty(self):
        assert SandboxBackendStrategy().available_backends([]) == []

    def test_none_available_only(self):
        caps = [_make_cap(SandboxBackend.NONE, True)]
        result = SandboxBackendStrategy().available_backends(caps)
        assert result == [SandboxBackend.NONE]


class TestDescribe:
    def test_describe_known_backend(self):
        caps = [
            SandboxCapability(
                backend=SandboxBackend.DOCKER,
                available=True,
                supported_platforms=["Linux", "macOS"],
                reason="Docker CLI is available at /usr/bin/docker.",
            )
        ]
        desc = SandboxBackendStrategy().describe(SandboxBackend.DOCKER, caps)
        assert "Docker" in desc

    def test_describe_missing_backend_returns_not_found(self):
        desc = SandboxBackendStrategy().describe(SandboxBackend.DOCKER, [])
        assert "not found" in desc.lower()

    def test_describe_returns_capability_reason(self):
        caps = [_make_cap(SandboxBackend.MACOS_SEATBELT, False)]
        desc = SandboxBackendStrategy().describe(SandboxBackend.MACOS_SEATBELT, caps)
        assert "macos_seatbelt reason" in desc


class TestStrategyIsolation:
    """Strategy must not depend on CLI, planner, audit, or file I/O."""

    def test_no_project_root_needed(self):
        # Instantiate and call without any project root or config
        strategy = SandboxBackendStrategy()
        caps = [_make_cap(SandboxBackend.DOCKER, True)]
        result = strategy.recommend(caps)
        assert result == SandboxBackend.DOCKER

    def test_recommend_is_deterministic(self):
        caps = [
            _make_cap(SandboxBackend.DOCKER, True),
            _make_cap(SandboxBackend.MACOS_SEATBELT, True),
        ]
        strategy = SandboxBackendStrategy()
        results = {strategy.recommend(caps) for _ in range(10)}
        assert len(results) == 1

    def test_recommend_does_not_mutate_input(self):
        caps = [
            _make_cap(SandboxBackend.DOCKER, True),
            _make_cap(SandboxBackend.NONE, True),
        ]
        original_len = len(caps)
        SandboxBackendStrategy().recommend(caps)
        assert len(caps) == original_len


class TestPlannerDelegates:
    """SandboxPlanner must use SandboxBackendStrategy for recommendation."""

    def test_planner_has_strategy_attribute(self, tmp_path):
        from safecode.sandbox.planner import SandboxPlanner
        planner = SandboxPlanner(tmp_path)
        assert hasattr(planner, "strategy")
        assert isinstance(planner.strategy, SandboxBackendStrategy)

    def test_planner_recommend_removed(self, tmp_path):
        from safecode.sandbox.planner import SandboxPlanner
        planner = SandboxPlanner(tmp_path)
        assert not hasattr(planner, "_recommend"), (
            "SandboxPlanner._recommend() should be removed; "
            "recommendation is delegated to SandboxBackendStrategy"
        )
