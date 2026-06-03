"""Bounded concurrent subagent pool (T-3.4.0-A / T-3.4.1-A).

Provides a fixed-size worker pool that dispatches multiple read-only
subagent requests concurrently, enforces a configurable cap, returns
results sorted deterministically by task_id, and supports idempotent
parent-side cancellation.

Default max concurrency: 2 (override via SAFECODE_SUBAGENT_MAX env var).
"""

from __future__ import annotations

import os
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from safecode.config import SafeCodeConfig
from safecode.subagents.executor import SubagentDispatchExecutor, SubagentRequest, SubagentResult

_DEFAULT_MAX_WORKERS: int = 2
_ABS_MAX_WORKERS: int = 32
_ENV_MAX_WORKERS: str = "SAFECODE_SUBAGENT_MAX"


def _resolve_max_workers(override: Optional[int] = None) -> int:
    """Resolve the max concurrent workers: override → env → default.

    Invalid env values fail closed with a RuntimeWarning and fall back to
    the default (2). Never crashes normal runs.
    """
    if override is not None:
        return max(1, min(override, _ABS_MAX_WORKERS))
    raw = os.environ.get(_ENV_MAX_WORKERS)
    if raw is not None:
        try:
            v = int(raw)
            if v < 1:
                warnings.warn(
                    f"{_ENV_MAX_WORKERS}={raw!r} must be >= 1; "
                    f"using default {_DEFAULT_MAX_WORKERS}.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return _DEFAULT_MAX_WORKERS
            return min(v, _ABS_MAX_WORKERS)
        except (ValueError, TypeError):
            warnings.warn(
                f"{_ENV_MAX_WORKERS}={raw!r} is not a valid integer; "
                f"using default {_DEFAULT_MAX_WORKERS}.",
                RuntimeWarning,
                stacklevel=2,
            )
    return _DEFAULT_MAX_WORKERS


class CancellationToken:
    """Thread-safe idempotent cancellation token (T-3.4.1-A).

    Preferred over ad-hoc booleans: backed by threading.Event, safe to
    call from any thread, and cancel() is idempotent.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation. Safe to call multiple times."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Return True if cancel() has been called at least once."""
        return self._event.is_set()


class SubagentPool:
    """Bounded concurrent subagent dispatcher with idempotent cancellation.

    Limits concurrency to at most ``max_workers`` tasks at once (default 2,
    configurable via ``SAFECODE_SUBAGENT_MAX``). Results are always returned
    sorted by ``task_id`` for deterministic ordering regardless of completion
    order. Exceptions in one worker do not corrupt results from other workers.

    Cancellation (T-3.4.1-A):
    - Pass a ``CancellationToken`` to ``run_all`` to allow parent-side revocation.
    - Tasks that have not started when the token is cancelled are marked blocked.
    - ``cancel()`` on the pool itself signals the pool's internal token.
    - No orphan task files or dangling threads are left after cancellation.

    Example::

        pool = SubagentPool(project_root, max_workers=2)
        results = pool.run_all([req1, req2, req3])
        # results sorted by task_id
    """

    def __init__(
        self,
        project_root: Path,
        config: Optional[SafeCodeConfig] = None,
        *,
        max_workers: Optional[int] = None,
        executor: Optional[SubagentDispatchExecutor] = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.max_workers = _resolve_max_workers(max_workers)
        self._injected_executor = executor
        self._token = CancellationToken()

    def cancel(self) -> None:
        """Cancel all pending/future subagent runs on this pool. Idempotent."""
        self._token.cancel()

    def run_all(
        self,
        requests: list[SubagentRequest],
        *,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> list[SubagentResult]:
        """Dispatch all requests with bounded concurrency.

        Returns a list of SubagentResult values sorted by task_id (ascending)
        for deterministic ordering. Cancelled tasks are returned as blocked
        results (blocked=True, task_id=""). Worker exceptions are caught and
        returned as blocked results; they do not affect other tasks.

        Args:
            requests: Subagent requests to run. May be empty.
            cancellation_token: External token; if already cancelled, all
                tasks are immediately marked blocked. If None, uses the pool's
                own internal token.
        """
        if not requests:
            return []

        token = cancellation_token if cancellation_token is not None else self._token

        def _run_one(req: SubagentRequest) -> SubagentResult:
            if token.is_cancelled():
                return SubagentResult(
                    task_id="",
                    summary="Subagent cancelled before execution.",
                    blocked=True,
                    success=False,
                )
            ex = (
                self._injected_executor
                or SubagentDispatchExecutor(self.project_root, self.config)
            )
            return ex.execute(req.task, req.scope, req.max_steps)

        result_by_idx: dict[int, SubagentResult] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map = {pool.submit(_run_one, req): i for i, req in enumerate(requests)}
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    result_by_idx[idx] = future.result()
                except Exception as exc:
                    result_by_idx[idx] = SubagentResult(
                        task_id="",
                        summary=f"Worker exception: {type(exc).__name__}",
                        errors=[type(exc).__name__],
                        blocked=True,
                        success=False,
                    )

        all_results = [result_by_idx[i] for i in range(len(requests))]
        return sorted(all_results, key=lambda r: r.task_id)
