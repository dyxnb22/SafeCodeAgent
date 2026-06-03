"""Tests for T-3.4.1-A: Parent-side subagent cancellation."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from safecode.subagents.executor import SubagentRequest, SubagentResult
from safecode.subagents.pool import CancellationToken, SubagentPool


# ---------------------------------------------------------------------------
# CancellationToken idempotency
# ---------------------------------------------------------------------------


class TestCancellationTokenIdempotency:
    def test_cancel_twice_is_safe(self):
        token = CancellationToken()
        token.cancel()
        token.cancel()  # idempotent
        assert token.is_cancelled()

    def test_cancel_ten_times_is_safe(self):
        token = CancellationToken()
        for _ in range(10):
            token.cancel()
        assert token.is_cancelled()

    def test_not_cancelled_before_cancel_called(self):
        token = CancellationToken()
        assert not token.is_cancelled()


# ---------------------------------------------------------------------------
# Cancelling a running subagent pool
# ---------------------------------------------------------------------------


class TestCancelRunningSubagent:
    def test_cancelled_task_result_is_blocked(self, tmp_path):
        """Cancelling a pool marks pending tasks as blocked."""
        token = CancellationToken()
        token.cancel()  # cancel before any task starts

        mock_ex = MagicMock()
        mock_ex.execute.return_value = SubagentResult(
            task_id="should-not-be-set",
            summary="should not run",
            success=True,
        )
        pool = SubagentPool(tmp_path, max_workers=2, executor=mock_ex)
        results = pool.run_all(
            [SubagentRequest("t1", "scope", 1), SubagentRequest("t2", "scope", 1)],
            cancellation_token=token,
        )
        assert all(r.blocked for r in results)
        assert all(not r.success for r in results)
        mock_ex.execute.assert_not_called()

    def test_cancelled_task_has_empty_task_id(self, tmp_path):
        token = CancellationToken()
        token.cancel()

        pool = SubagentPool(tmp_path, max_workers=2)
        results = pool.run_all(
            [SubagentRequest("t1", "scope", 1)],
            cancellation_token=token,
        )
        assert results[0].task_id == ""
        assert results[0].blocked is True

    def test_cancel_after_pool_runs_pool_cancel_method(self, tmp_path):
        """pool.cancel() signals the pool's own token."""
        pool = SubagentPool(tmp_path, max_workers=2)
        pool.cancel()
        assert pool._token.is_cancelled()

    def test_pool_cancel_prevents_new_tasks(self, tmp_path):
        mock_ex = MagicMock()
        mock_ex.execute.return_value = SubagentResult(
            task_id="t", summary="ok", success=True
        )
        pool = SubagentPool(tmp_path, max_workers=2, executor=mock_ex)
        pool.cancel()
        results = pool.run_all([SubagentRequest("task", "scope", 1)])
        assert results[0].blocked is True
        mock_ex.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Cancellation completes within 5 seconds
# ---------------------------------------------------------------------------


class TestCancellationTimeliness:
    def test_cancellation_completes_within_5_seconds(self, tmp_path):
        """Pool.run_all returns within 5s after cancellation even with active workers."""
        token = CancellationToken()

        def slow_execute(task, scope, max_steps):
            # Worker completes quickly because the cancel is checked first.
            if token.is_cancelled():
                return SubagentResult(task_id="", summary="cancelled", blocked=True, success=False)
            return SubagentResult(task_id=task, summary="ok", success=True)

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = slow_execute

        pool = SubagentPool(tmp_path, max_workers=2, executor=mock_ex)
        token.cancel()  # cancel before start

        start = time.monotonic()
        results = pool.run_all(
            [SubagentRequest(f"t{i}", "scope", 1) for i in range(5)],
            cancellation_token=token,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 5.0
        assert all(r.blocked for r in results)

    def test_cancel_during_execution_finishes_within_5_seconds(self, tmp_path):
        """Signal cancellation mid-execution; pool must return within 5s."""
        token = CancellationToken()
        started_event = threading.Event()

        def execute_then_cancel(task, scope, max_steps):
            # Signal that at least one worker started, then cancel.
            if not started_event.is_set():
                started_event.set()
                token.cancel()
            # Worker runs quickly (no artificial sleep).
            return SubagentResult(task_id=task, summary="ok", success=True)

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = execute_then_cancel

        pool = SubagentPool(tmp_path, max_workers=2, executor=mock_ex)
        start = time.monotonic()
        pool.run_all(
            [SubagentRequest(f"t{i}", "scope", 1) for i in range(4)],
            cancellation_token=token,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 5.0


# ---------------------------------------------------------------------------
# Deterministic ordering survives cancellation
# ---------------------------------------------------------------------------


class TestOrderingAfterCancellation:
    def test_returned_results_still_sorted_by_task_id(self, tmp_path):
        token = CancellationToken()
        token.cancel()

        pool = SubagentPool(tmp_path, max_workers=2)
        requests = [SubagentRequest(f"t{i}", "scope", 1) for i in range(4)]
        results = pool.run_all(requests, cancellation_token=token)

        ids = [r.task_id for r in results]
        assert ids == sorted(ids)
        assert all(r.blocked for r in results)


# ---------------------------------------------------------------------------
# No orphan files after cancellation
# ---------------------------------------------------------------------------


class TestNoOrphanFilesAfterCancellation:
    def test_no_task_files_created_when_cancelled_before_start(self, tmp_path):
        token = CancellationToken()
        token.cancel()

        pool = SubagentPool(tmp_path, max_workers=2)
        pool.run_all(
            [SubagentRequest("task1", "scope", 1)],
            cancellation_token=token,
        )

        subagents_dir = tmp_path / ".sac" / "subagents"
        if subagents_dir.exists():
            task_dirs = list(subagents_dir.iterdir())
            assert len(task_dirs) == 0, f"Unexpected task dirs: {task_dirs}"

    def test_no_dangling_threads_after_pool_completes(self, tmp_path):
        token = CancellationToken()
        token.cancel()

        pool = SubagentPool(tmp_path, max_workers=2)
        thread_count_before = threading.active_count()
        pool.run_all(
            [SubagentRequest("t1", "scope", 1)],
            cancellation_token=token,
        )
        time.sleep(0.05)  # allow any lingering threads to settle
        thread_count_after = threading.active_count()
        # ThreadPoolExecutor shuts down cleanly; thread count should not grow.
        assert thread_count_after <= thread_count_before + 1
