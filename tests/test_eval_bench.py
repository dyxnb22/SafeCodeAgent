"""Tests for v3.10.0 sac eval bench.

Covers:
- BenchFixtureResult data model
- EvalBenchRunner determinism (mocked clock, no wall-time brittleness)
- Snapshot write on first run
- Regression detection within ±20% tolerance
- CLI sac eval --mode bench exits 0
- Patch hash stability
"""

from __future__ import annotations

import json
import itertools
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.eval.bench import (
    BenchFixtureResult,
    BenchRegressionReport,
    BenchRunSummary,
    EvalBenchRunner,
    _TIME_TOLERANCE,
    _compute_patch_hash,
    _check_regression,
    _load_baseline,
    _snapshot_path,
    _write_baseline,
    render_bench_summary,
)
from safecode.eval.loop_runner import default_loop_fixtures

runner = CliRunner()


# ── Data model ────────────────────────────────────────────────────────────


class TestBenchFixtureResult:
    def test_as_dict_has_required_keys(self):
        r = BenchFixtureResult(
            fixture_name="test-fixture",
            wall_time_seconds=0.1234,
            step_count=3,
            patch_output_hash="abc123",
            passed=True,
        )
        d = r.as_dict()
        assert d["fixture_name"] == "test-fixture"
        assert d["wall_time_seconds"] == pytest.approx(0.1234)
        assert d["step_count"] == 3
        assert d["patch_output_hash"] == "abc123"
        assert d["passed"] is True
        assert "failure_reasons" in d

    def test_as_dict_is_json_serializable(self):
        r = BenchFixtureResult("f", 0.5, 2, None, False, ["bad thing"])
        assert json.dumps(r.as_dict())

    def test_wall_time_rounded_in_dict(self):
        r = BenchFixtureResult("f", 1.123456789, 1, None, True)
        d = r.as_dict()
        # rounded to 4dp
        assert d["wall_time_seconds"] == pytest.approx(1.1235, abs=1e-3)

    def test_no_patch_hash_is_none(self):
        r = BenchFixtureResult("f", 0.1, 1, None, True)
        assert r.as_dict()["patch_output_hash"] is None


# ── Patch hash ────────────────────────────────────────────────────────────


class TestPatchHash:
    def test_none_for_empty_text(self):
        assert _compute_patch_hash("") is None
        assert _compute_patch_hash(None) is None
        assert _compute_patch_hash("   ") is None

    def test_stable_for_same_input(self):
        h1 = _compute_patch_hash("hello patch")
        h2 = _compute_patch_hash("hello patch")
        assert h1 == h2

    def test_different_for_different_input(self):
        assert _compute_patch_hash("a") != _compute_patch_hash("b")

    def test_is_sha256_hex(self):
        h = _compute_patch_hash("some patch")
        assert h is not None
        assert len(h) == 64
        int(h, 16)  # valid hex


# ── Snapshot helpers ──────────────────────────────────────────────────────


class TestSnapshotHelpers:
    def test_snapshot_path_sanitizes_name(self, tmp_path):
        p = _snapshot_path(tmp_path, "my fixture/name")
        assert "/" not in p.name
        assert p.suffix == ".json"

    def test_load_baseline_returns_none_missing(self, tmp_path):
        assert _load_baseline(tmp_path, "nonexistent") is None

    def test_load_baseline_returns_dict_if_present(self, tmp_path):
        r = BenchFixtureResult("f", 0.2, 2, None, True)
        _write_baseline(tmp_path, r)
        data = _load_baseline(tmp_path, "f")
        assert data is not None
        assert data["fixture_name"] == "f"

    def test_write_baseline_creates_valid_json(self, tmp_path):
        r = BenchFixtureResult("my-fix", 0.3, 4, "abc", True)
        _write_baseline(tmp_path, r)
        path = _snapshot_path(tmp_path, "my-fix")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["step_count"] == 4


# ── Regression detection ──────────────────────────────────────────────────


class TestRegressionDetection:
    def _make_result(self, name: str, t: float) -> BenchFixtureResult:
        return BenchFixtureResult(name, t, 2, None, True)

    def test_no_regression_within_tolerance(self):
        result = self._make_result("f", 0.105)
        baseline = {"wall_time_seconds": 0.1}
        reg = _check_regression(result, baseline)
        assert not reg.regression

    def test_regression_detected_above_tolerance(self):
        result = self._make_result("f", 0.13)
        baseline = {"wall_time_seconds": 0.1}
        reg = _check_regression(result, baseline)
        assert reg.regression

    def test_faster_is_not_regression(self):
        result = self._make_result("f", 0.085)
        baseline = {"wall_time_seconds": 0.1}
        reg = _check_regression(result, baseline)
        assert not reg.regression  # 15% faster, within tolerance

    def test_regression_too_fast_outside_tolerance(self):
        result = self._make_result("f", 0.05)
        baseline = {"wall_time_seconds": 0.1}
        reg = _check_regression(result, baseline)
        assert reg.regression  # 50% faster, outside tolerance

    def test_none_baseline_time_skips(self):
        result = self._make_result("f", 0.1)
        reg = _check_regression(result, {"wall_time_seconds": None})
        assert not reg.regression
        assert "skipping" in reg.message.lower()

    def test_zero_baseline_time_skips(self):
        result = self._make_result("f", 0.1)
        reg = _check_regression(result, {"wall_time_seconds": 0})
        assert not reg.regression

    def test_tolerance_constant_is_20_percent(self):
        assert _TIME_TOLERANCE == pytest.approx(0.20)


# ── EvalBenchRunner ───────────────────────────────────────────────────────


class TestEvalBenchRunner:
    def _make_clock(self, times: list[float]):
        """Return a callable that returns successive values from times."""
        it = iter(times)
        def clock():
            try:
                return next(it)
            except StopIteration:
                return 0.0
        return clock

    def test_run_fixture_returns_result(self, tmp_path):
        fixtures = default_loop_fixtures()[:1]
        clock = self._make_clock([0.0, 0.1])
        bench = EvalBenchRunner(snapshot_dir=tmp_path, clock=clock)
        result = bench.run_fixture(fixtures[0])
        assert isinstance(result, BenchFixtureResult)
        assert result.fixture_name == fixtures[0].name
        assert result.step_count == len(fixtures[0].scripted_steps)
        assert result.wall_time_seconds >= 0.0

    def test_run_all_writes_baseline_on_first_run(self, tmp_path):
        # Inject fast clock: pairs of (t0, t1) for each fixture
        fixtures = default_loop_fixtures()
        times = list(itertools.chain.from_iterable((i * 0.1, i * 0.1 + 0.05) for i in range(len(fixtures))))
        clock = self._make_clock(times)
        bench = EvalBenchRunner(snapshot_dir=tmp_path, clock=clock)
        summary = bench.run_all(fixtures)
        assert summary.snapshot_written
        assert len(summary.results) == len(fixtures)
        # Snapshot files should exist
        for r in summary.results:
            p = _snapshot_path(tmp_path, r.fixture_name)
            assert p.exists(), f"Snapshot missing for {r.fixture_name}"

    def test_run_all_no_regression_on_second_run_same_time(self, tmp_path):
        fixtures = default_loop_fixtures()[:2]
        # First run: write baseline
        times1 = list(itertools.chain.from_iterable((0.0, 0.1) for _ in fixtures))
        bench1 = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock(times1))
        bench1.run_all(fixtures)
        # Second run: same timing → no regression
        times2 = list(itertools.chain.from_iterable((0.0, 0.1) for _ in fixtures))
        bench2 = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock(times2))
        summary = bench2.run_all(fixtures)
        assert not summary.snapshot_written
        for reg in summary.regressions:
            assert not reg.regression, f"Unexpected regression: {reg.message}"

    def test_run_all_detects_regression(self, tmp_path):
        fixtures = default_loop_fixtures()[:1]
        # Baseline: 0.1s
        bench1 = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock([0.0, 0.1]))
        bench1.run_all(fixtures)
        # Second run: 0.5s (400% slower)
        bench2 = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock([0.0, 0.5]))
        summary = bench2.run_all(fixtures)
        assert any(r.regression for r in summary.regressions)

    def test_update_baseline_overwrites(self, tmp_path):
        fixtures = default_loop_fixtures()[:1]
        bench1 = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock([0.0, 0.1]))
        bench1.run_all(fixtures)
        bench2 = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock([0.0, 0.9]))
        summary = bench2.run_all(fixtures, update_baseline=True)
        assert summary.snapshot_written

    def test_summary_all_passed_attribute(self, tmp_path):
        fixtures = default_loop_fixtures()
        times = list(itertools.chain.from_iterable((0.0, 0.05) for _ in fixtures))
        bench = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock(times))
        summary = bench.run_all(fixtures)
        assert isinstance(summary.all_passed, bool)

    def test_summary_as_dict_is_json_serializable(self, tmp_path):
        fixtures = default_loop_fixtures()[:2]
        times = list(itertools.chain.from_iterable((0.0, 0.1) for _ in fixtures))
        bench = EvalBenchRunner(snapshot_dir=tmp_path, clock=self._make_clock(times))
        summary = bench.run_all(fixtures)
        assert json.dumps(summary.as_dict())


# ── Render ────────────────────────────────────────────────────────────────


class TestRenderBenchSummary:
    def test_render_contains_fixture_names(self, tmp_path):
        fixtures = default_loop_fixtures()[:2]
        import itertools as _it
        times = list(_it.chain.from_iterable((0.0, 0.05) for _ in fixtures))
        bench = EvalBenchRunner(snapshot_dir=tmp_path, clock=lambda: times.pop(0) if times else 0.0)
        summary = bench.run_all(fixtures)
        text = render_bench_summary(summary)
        for r in summary.results:
            assert r.fixture_name in text

    def test_render_is_string(self, tmp_path):
        fixtures = default_loop_fixtures()[:1]
        bench = EvalBenchRunner(snapshot_dir=tmp_path, clock=lambda: 0.0)
        summary = bench.run_all(fixtures)
        assert isinstance(render_bench_summary(summary), str)


# ── CLI integration ───────────────────────────────────────────────────────


class TestEvalBenchCLI:
    def test_bench_mode_exits_zero(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "bench"], catch_exceptions=False)
        assert result.exit_code == 0, f"Exit {result.exit_code}:\n{result.output}"

    def test_bench_mode_output_contains_fixture_names(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "bench"], catch_exceptions=False)
        for name in ("docs-edit", "python-function-fix"):
            assert name in result.output

    def test_bench_mode_no_network_markers(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["eval", "--mode", "bench"], catch_exceptions=False)
        assert "openai" not in result.output.lower()
        assert "anthropic" not in result.output.lower()
