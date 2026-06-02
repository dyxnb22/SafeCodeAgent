"""Sandbox backend selection strategy.

Separates capability-based recommendation from SandboxPlanner, which adds
auditing and plan composition. This module is pure: no I/O, no audit events,
no subprocess calls. Use it to test recommendation logic independently of
CLI rendering or proposal execution.
"""

from __future__ import annotations

from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability


class SandboxBackendStrategy:
    """Recommend a sandbox backend given a list of detected capabilities.

    Holds no state and performs no side effects. Safe to instantiate and call
    in tests without a project root or config.
    """

    # Priority order: strongest isolation first, Noop as final fallback.
    _PRIORITY = [
        SandboxBackend.LINUX_BUBBLEWRAP,
        SandboxBackend.MACOS_SEATBELT,
        SandboxBackend.DOCKER,
    ]

    def recommend(self, capabilities: list[SandboxCapability]) -> SandboxBackend:
        """Return the highest-priority available backend.

        Iterates the fixed priority order and returns the first backend that
        is both present in *capabilities* and marked available. Falls back to
        ``SandboxBackend.NONE`` when nothing stronger is available.
        """
        by_backend = {cap.backend: cap for cap in capabilities}
        for backend in self._PRIORITY:
            cap = by_backend.get(backend)
            if cap is not None and cap.available:
                return backend
        return SandboxBackend.NONE

    def available_backends(self, capabilities: list[SandboxCapability]) -> list[SandboxBackend]:
        """Return all available backends in priority order, including NONE."""
        by_backend = {cap.backend: cap for cap in capabilities}
        result: list[SandboxBackend] = []
        for backend in self._PRIORITY:
            cap = by_backend.get(backend)
            if cap is not None and cap.available:
                result.append(backend)
        none_cap = by_backend.get(SandboxBackend.NONE)
        if none_cap is not None and none_cap.available:
            result.append(SandboxBackend.NONE)
        return result

    def describe(self, backend: SandboxBackend, capabilities: list[SandboxCapability]) -> str:
        """Return a short reason string for the given backend from capabilities."""
        by_backend = {cap.backend: cap for cap in capabilities}
        cap = by_backend.get(backend)
        if cap is None:
            return f"Backend {backend.value!r} not found in detected capabilities."
        return cap.reason
