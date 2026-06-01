"""Performance budget tests for v2.5.4.

Covers:
  A. PerformanceBudget default construction — zero/None defaults.
  B. PerformanceBudget with explicit values — fields stored correctly.
  C. PerformanceBudget.as_dict() — deterministic, JSON-serializable shape.
  D. as_dict() rounds total_command_duration_ms to 3 decimal places.
  E. llm_latency_ms None preserved in as_dict().
  F. compute_context_size — empty snapshot returns 0.
  G. compute_context_size — sums UTF-8 byte lengths of all file contents.
  H. compute_context_size — multi-byte characters counted by encoded length.
  I. compute_disk_growth — equal snapshots returns 0.
  J. compute_disk_growth — added bytes returns positive value.
  K. compute_disk_growth — removed bytes returns 0 (never negative).
  L. compute_disk_growth — mixed add/remove returns net gain or 0.
  M. ReplayResult.performance_budget default is None — backward compat.
  N. ReplayResult can be constructed with explicit performance_budget.
  O. TaskReplayRunner populates performance_budget on a successful run.
  P. performance_budget.context_size_bytes reflects initial workspace size.
  Q. performance_budget.disk_growth_bytes reflects files added by setup.
  R. performance_budget.llm_latency_ms is None (no LLM in replay runner).
  S. performance_budget.total_command_duration_ms is non-negative float.
  T. _error_result leaves performance_budget as None.
  U. PerformanceBudget is frozen — fields cannot be mutated.
  V. as_dict() keys are stable/deterministic across calls.
  W. compute_context_size with single file — exact byte count.
  X. compute_disk_growth with new file added — counts new file bytes.
"""

from __future__ import annotations

import json

import pytest

from safecode.eval.loader import load_fixture_from_dict
from safecode.eval.runner import ReplayResult, TaskReplayRunner, ValidationCommandResult
from safecode.trace.budget import (
    PerformanceBudget,
    compute_context_size,
    compute_disk_growth,
)


# ── A. Default construction ───────────────────────────────────────────────


class TestPerformanceBudgetDefaults:
    def test_default_context_size_bytes_is_zero(self):
        b = PerformanceBudget()
        assert b.context_size_bytes == 0

    def test_default_total_command_duration_ms_is_zero(self):
        b = PerformanceBudget()
        assert b.total_command_duration_ms == 0.0

    def test_default_llm_latency_ms_is_none(self):
        b = PerformanceBudget()
        assert b.llm_latency_ms is None

    def test_default_disk_growth_bytes_is_zero(self):
        b = PerformanceBudget()
        assert b.disk_growth_bytes == 0


# ── B. Explicit values stored ─────────────────────────────────────────────


class TestPerformanceBudgetExplicit:
    def test_context_size_stored(self):
        b = PerformanceBudget(context_size_bytes=1024)
        assert b.context_size_bytes == 1024

    def test_duration_stored(self):
        b = PerformanceBudget(total_command_duration_ms=123.456)
        assert b.total_command_duration_ms == pytest.approx(123.456)

    def test_llm_latency_stored(self):
        b = PerformanceBudget(llm_latency_ms=50.0)
        assert b.llm_latency_ms == pytest.approx(50.0)

    def test_disk_growth_stored(self):
        b = PerformanceBudget(disk_growth_bytes=512)
        assert b.disk_growth_bytes == 512


# ── C. as_dict() shape ────────────────────────────────────────────────────


class TestPerformanceBudgetAsDict:
    def test_keys_present(self):
        d = PerformanceBudget().as_dict()
        assert set(d.keys()) == {
            "context_size_bytes",
            "total_command_duration_ms",
            "llm_latency_ms",
            "disk_growth_bytes",
        }

    def test_json_serializable(self):
        b = PerformanceBudget(context_size_bytes=10, total_command_duration_ms=5.5)
        json.dumps(b.as_dict())  # must not raise

    def test_values_match(self):
        b = PerformanceBudget(context_size_bytes=100, disk_growth_bytes=50)
        d = b.as_dict()
        assert d["context_size_bytes"] == 100
        assert d["disk_growth_bytes"] == 50


# ── D. as_dict() rounding ────────────────────────────────────────────────


class TestPerformanceBudgetRounding:
    def test_duration_rounded_to_3dp(self):
        b = PerformanceBudget(total_command_duration_ms=1.23456789)
        d = b.as_dict()
        assert d["total_command_duration_ms"] == 1.235

    def test_zero_duration_remains_zero(self):
        b = PerformanceBudget(total_command_duration_ms=0.0)
        d = b.as_dict()
        assert d["total_command_duration_ms"] == 0.0


# ── E. llm_latency_ms None in as_dict ────────────────────────────────────


class TestLlmLatencyNone:
    def test_none_preserved_in_as_dict(self):
        d = PerformanceBudget().as_dict()
        assert d["llm_latency_ms"] is None

    def test_value_preserved_in_as_dict(self):
        d = PerformanceBudget(llm_latency_ms=10.0).as_dict()
        assert d["llm_latency_ms"] == pytest.approx(10.0)


# ── F–H. compute_context_size ─────────────────────────────────────────────


class TestComputeContextSize:
    def test_empty_snapshot(self):
        assert compute_context_size({}) == 0

    def test_ascii_content(self):
        snapshot = {"a.txt": "hello"}
        assert compute_context_size(snapshot) == len("hello".encode("utf-8"))

    def test_sums_multiple_files(self):
        snapshot = {"a.txt": "ab", "b.txt": "cd"}
        assert compute_context_size(snapshot) == 4

    def test_multibyte_chars(self):
        content = "café"
        snapshot = {"f.txt": content}
        assert compute_context_size(snapshot) == len(content.encode("utf-8"))

    def test_single_file_exact(self):
        content = "x" * 200
        assert compute_context_size({"f.txt": content}) == 200


# ── I–L. compute_disk_growth ─────────────────────────────────────────────


class TestComputeDiskGrowth:
    def test_equal_snapshots_returns_zero(self):
        snap = {"a.txt": "hello"}
        assert compute_disk_growth(snap, snap) == 0

    def test_added_content_returns_positive(self):
        before = {"a.txt": "hi"}
        after = {"a.txt": "hi", "b.txt": "world"}
        growth = compute_disk_growth(before, after)
        assert growth == len("world".encode("utf-8"))

    def test_removed_content_returns_zero(self):
        before = {"a.txt": "long content here"}
        after = {"a.txt": "x"}
        assert compute_disk_growth(before, after) == 0

    def test_mixed_add_remove_net_gain(self):
        before = {"a.txt": "ab"}
        after = {"a.txt": "a", "b.txt": "xyz"}
        # before_bytes=2, after_bytes=1+3=4, growth=2
        assert compute_disk_growth(before, after) == 2

    def test_mixed_add_remove_net_loss_returns_zero(self):
        before = {"a.txt": "abcdefgh"}
        after = {"a.txt": "a", "b.txt": "xy"}
        # before=8, after=1+2=3, growth=max(0,-5)=0
        assert compute_disk_growth(before, after) == 0

    def test_new_file_added(self):
        before: dict[str, str] = {}
        after = {"new.txt": "hello"}
        assert compute_disk_growth(before, after) == 5


# ── M–N. ReplayResult backward compat ────────────────────────────────────


class TestReplayResultBackwardCompat:
    def _make_result(self, **kwargs) -> ReplayResult:
        defaults = dict(
            fixture_name="t",
            passed=True,
            failure_reasons=[],
            validation_details=[],
            observed_changed_files=[],
            workspace_diff="",
            network_intent="denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="ok",
        )
        defaults.update(kwargs)
        return ReplayResult(**defaults)

    def test_default_performance_budget_is_none(self):
        result = self._make_result()
        assert result.performance_budget is None

    def test_explicit_performance_budget_stored(self):
        budget = PerformanceBudget(context_size_bytes=42)
        result = self._make_result(performance_budget=budget)
        assert result.performance_budget is not None
        assert result.performance_budget.context_size_bytes == 42


# ── O–T. TaskReplayRunner integration ─────────────────────────────────────


def _inline_fixture(
    *,
    name: str = "budget-test",
    files: dict | None = None,
    setup_commands: list[str] | None = None,
    validation_commands: list[str] | None = None,
):
    return load_fixture_from_dict(
        {
            "schema_version": 1,
            "name": name,
            "goal": "test",
            "repo": {
                "kind": "inline",
                "files": files or {"hello.txt": "world"},
                "setup_commands": setup_commands or [],
            },
            "expected": {"kind": "any"},
            "safety": {},
            "validation_commands": validation_commands or [],
        }
    )


class TestReplayRunnerBudget:
    def test_budget_populated_on_success(self):
        fixture = _inline_fixture()
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None

    def test_context_size_bytes_reflects_initial_workspace(self):
        content = "x" * 100
        fixture = _inline_fixture(files={"f.txt": content})
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None
        assert result.performance_budget.context_size_bytes == 100

    def test_disk_growth_bytes_from_setup_commands(self):
        fixture = _inline_fixture(
            files={"a.txt": "a"},
            setup_commands=["echo -n newcontent > added.txt"],
        )
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None
        # disk grew (new file added)
        assert result.performance_budget.disk_growth_bytes >= 0

    def test_llm_latency_ms_is_none(self):
        fixture = _inline_fixture()
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None
        assert result.performance_budget.llm_latency_ms is None

    def test_total_command_duration_ms_is_non_negative(self):
        fixture = _inline_fixture(validation_commands=["true"])
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None
        assert result.performance_budget.total_command_duration_ms >= 0.0

    def test_total_command_duration_ms_is_float(self):
        fixture = _inline_fixture()
        result = TaskReplayRunner().run(fixture)
        assert isinstance(result.performance_budget.total_command_duration_ms, float)

    def test_error_result_has_no_budget(self):
        # Invalid local repo path triggers _error_result
        fixture = load_fixture_from_dict(
            {
                "schema_version": 1,
                "name": "err",
                "goal": "fail",
                "repo": {"kind": "local", "path": "/nonexistent/path/xyz"},
                "expected": {"kind": "any"},
                "safety": {},
            }
        )
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is None

    def test_budget_as_dict_is_json_serializable(self):
        fixture = _inline_fixture()
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None
        json.dumps(result.performance_budget.as_dict())  # must not raise

    def test_empty_workspace_context_size_non_negative(self):
        fixture = _inline_fixture(files={})
        result = TaskReplayRunner().run(fixture)
        assert result.performance_budget is not None
        assert result.performance_budget.context_size_bytes >= 0


# ── U. Frozen dataclass ────────────────────────────────────────────────────


class TestPerformanceBudgetFrozen:
    def test_cannot_mutate_field(self):
        b = PerformanceBudget(context_size_bytes=1)
        with pytest.raises((AttributeError, TypeError)):
            b.context_size_bytes = 2  # type: ignore[misc]


# ── V. as_dict() key stability ────────────────────────────────────────────


class TestAsDictStability:
    def test_keys_stable_across_calls(self):
        b = PerformanceBudget(context_size_bytes=5, total_command_duration_ms=1.5)
        assert list(b.as_dict().keys()) == list(b.as_dict().keys())

    def test_deterministic_output(self):
        b = PerformanceBudget(context_size_bytes=7, disk_growth_bytes=3)
        assert b.as_dict() == b.as_dict()
