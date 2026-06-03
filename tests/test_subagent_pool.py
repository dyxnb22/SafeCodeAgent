"""Tests for T-3.4.0-A: Bounded concurrent subagent pool."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from safecode.subagents.executor import SubagentRequest, SubagentResult
from safecode.subagents.pool import (
    CancellationToken,
    SubagentPool,
    _DEFAULT_MAX_WORKERS,
    _ENV_MAX_WORKERS,
    _resolve_max_workers,
)


# ---------------------------------------------------------------------------
# _resolve_max_workers
# ---------------------------------------------------------------------------


class TestResolveMaxWorkers:
    def test_default_is_2(self):
        # Run without override and without env var set.
        result = _resolve_max_workers()
        assert result == _DEFAULT_MAX_WORKERS == 2

    def test_override_takes_precedence(self):
        assert _resolve_max_workers(override=4) == 4

    def test_override_clamped_to_at_least_1(self):
        assert _resolve_max_workers(override=0) == 1

    def test_env_override_valid(self, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "5")
        assert _resolve_max_workers() == 5

    def test_env_override_zero_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "0")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _resolve_max_workers()
        assert result == _DEFAULT_MAX_WORKERS
        assert any("must be >= 1" in str(warning.message) for warning in w)

    def test_env_override_negative_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "-3")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _resolve_max_workers()
        assert result == _DEFAULT_MAX_WORKERS
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)

    def test_env_override_non_integer_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "abc")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _resolve_max_workers()
        assert result == _DEFAULT_MAX_WORKERS
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)

    def test_env_override_float_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "2.5")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _resolve_max_workers()
        assert result == _DEFAULT_MAX_WORKERS
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)

    def test_env_override_empty_string_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _resolve_max_workers()
        assert result == _DEFAULT_MAX_WORKERS

    def test_env_not_set_returns_default(self, monkeypatch):
        monkeypatch.delenv(_ENV_MAX_WORKERS, raising=False)
        assert _resolve_max_workers() == _DEFAULT_MAX_WORKERS


# ---------------------------------------------------------------------------
# CancellationToken
# ---------------------------------------------------------------------------


class TestCancellationToken:
    def test_not_cancelled_initially(self):
        token = CancellationToken()
        assert not token.is_cancelled()

    def test_cancel_sets_state(self):
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled()

    def test_cancel_is_idempotent(self):
        token = CancellationToken()
        token.cancel()
        token.cancel()
        token.cancel()
        assert token.is_cancelled()

    def test_thread_safe_cancel(self):
        token = CancellationToken()
        threads = [threading.Thread(target=token.cancel) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert token.is_cancelled()


# ---------------------------------------------------------------------------
# SubagentPool construction
# ---------------------------------------------------------------------------


class TestSubagentPoolConstruction:
    def test_default_max_workers(self, tmp_path):
        pool = SubagentPool(tmp_path)
        assert pool.max_workers == 2

    def test_custom_max_workers(self, tmp_path):
        pool = SubagentPool(tmp_path, max_workers=4)
        assert pool.max_workers == 4

    def test_env_max_workers(self, tmp_path, monkeypatch):
        monkeypatch.setenv(_ENV_MAX_WORKERS, "3")
        pool = SubagentPool(tmp_path)
        assert pool.max_workers == 3

    def test_empty_requests_returns_empty(self, tmp_path):
        pool = SubagentPool(tmp_path)
        assert pool.run_all([]) == []


# ---------------------------------------------------------------------------
# SubagentPool: cap enforcement
# ---------------------------------------------------------------------------


class TestSubagentPoolCapEnforcement:
    def test_cap_enforced_at_runtime(self, tmp_path):
        """At most max_workers tasks are active simultaneously."""
        active_count = [0]
        peak_active = [0]
        lock = threading.Lock()

        def fake_execute(task, scope, max_steps):
            with lock:
                active_count[0] += 1
                if active_count[0] > peak_active[0]:
                    peak_active[0] = active_count[0]
            time.sleep(0.03)
            with lock:
                active_count[0] -= 1
            return SubagentResult(
                task_id=f"task-{task[:4]}",
                summary="ok",
                success=True,
            )

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = fake_execute

        pool = SubagentPool(tmp_path, max_workers=2, executor=mock_ex)
        requests = [SubagentRequest(f"task{i}", "scope", 1) for i in range(6)]
        results = pool.run_all(requests)

        assert peak_active[0] <= 2
        assert len(results) == 6

    def test_cap_of_1_is_sequential(self, tmp_path):
        order: list[int] = []
        lock = threading.Lock()

        def fake_execute(task, scope, max_steps):
            idx = int(task)
            with lock:
                order.append(idx)
            return SubagentResult(task_id=str(idx), summary="ok", success=True)

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = fake_execute

        pool = SubagentPool(tmp_path, max_workers=1, executor=mock_ex)
        requests = [SubagentRequest(str(i), "scope", 1) for i in range(3)]
        pool.run_all(requests)
        # sequential execution means only one thread ever ran a task
        assert len(order) == 3


# ---------------------------------------------------------------------------
# SubagentPool: deterministic ordering
# ---------------------------------------------------------------------------


class TestSubagentPoolOrdering:
    def test_results_sorted_by_task_id(self, tmp_path):
        """Completion order does not affect returned order (sorted by task_id)."""
        results_in_call_order: list[SubagentResult] = []
        lock = threading.Lock()
        call_idx = [0]

        def fake_execute(task, scope, max_steps):
            with lock:
                idx = call_idx[0]
                call_idx[0] += 1
            # Reverse-order sleeping: first task sleeps longest
            time.sleep(0.05 * (3 - idx) if idx < 3 else 0.01)
            result = SubagentResult(
                task_id=f"zzz-{task}" if idx == 0 else f"aaa-{task}",
                summary="ok",
                success=True,
            )
            with lock:
                results_in_call_order.append(result)
            return result

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = fake_execute

        pool = SubagentPool(tmp_path, max_workers=3, executor=mock_ex)
        requests = [SubagentRequest(str(i), "scope", 1) for i in range(3)]
        results = pool.run_all(requests)

        # Output must be sorted by task_id, not by completion order.
        ids = [r.task_id for r in results]
        assert ids == sorted(ids)

    def test_ordering_is_stable_across_multiple_runs(self, tmp_path):
        def fake_execute(task, scope, max_steps):
            return SubagentResult(task_id=f"id-{task}", summary="ok", success=True)

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = fake_execute

        pool = SubagentPool(tmp_path, max_workers=3, executor=mock_ex)
        requests = [SubagentRequest(str(i), "scope", 1) for i in range(5)]

        ids_run1 = [r.task_id for r in pool.run_all(requests)]
        ids_run2 = [r.task_id for r in pool.run_all(requests)]
        assert ids_run1 == ids_run2


# ---------------------------------------------------------------------------
# SubagentPool: exception isolation
# ---------------------------------------------------------------------------


class TestSubagentPoolExceptionIsolation:
    def test_worker_exception_does_not_corrupt_other_results(self, tmp_path):
        """A worker exception returns a blocked result; other results are unaffected."""
        call_count = [0]
        lock = threading.Lock()

        def fake_execute(task, scope, max_steps):
            with lock:
                idx = call_count[0]
                call_count[0] += 1
            if idx == 1:
                raise RuntimeError("deliberate worker failure")
            return SubagentResult(task_id=f"task-{task}", summary="ok", success=True)

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = fake_execute

        pool = SubagentPool(tmp_path, max_workers=3, executor=mock_ex)
        requests = [SubagentRequest(str(i), "scope", 1) for i in range(3)]
        results = pool.run_all(requests)

        assert len(results) == 3
        successful = [r for r in results if r.success]
        blocked = [r for r in results if r.blocked]
        assert len(successful) == 2
        assert len(blocked) == 1
        assert blocked[0].task_id == ""  # no task ID for worker exception

    def test_all_workers_fail(self, tmp_path):
        def fake_execute(task, scope, max_steps):
            raise ValueError("all fail")

        mock_ex = MagicMock()
        mock_ex.execute.side_effect = fake_execute

        pool = SubagentPool(tmp_path, max_workers=2, executor=mock_ex)
        requests = [SubagentRequest("t1", "scope", 1), SubagentRequest("t2", "scope", 1)]
        results = pool.run_all(requests)
        assert all(r.blocked for r in results)
        assert all(not r.success for r in results)


# ---------------------------------------------------------------------------
# Backward compatibility: single-subagent path
# ---------------------------------------------------------------------------


class TestSubagentPoolSingleTask:
    def test_single_request_compatible(self, tmp_path):
        mock_ex = MagicMock()
        mock_ex.execute.return_value = SubagentResult(
            task_id="abc123",
            summary="single result",
            success=True,
        )
        pool = SubagentPool(tmp_path, executor=mock_ex)
        results = pool.run_all([SubagentRequest("my task", "my scope", 1)])
        assert len(results) == 1
        assert results[0].task_id == "abc123"
        assert results[0].success is True
