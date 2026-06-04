"""Eval bench runner for v3.10.0.

Collects per-fixture metrics (wall time, step count, pending-patch hash)
and compares against a stored baseline snapshot within ±20% tolerance.

Baseline snapshots live under ``tests/snapshots/bench/`` and are written
on the first run (when no snapshot exists). Subsequent runs compare against
the stored baseline.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.eval.loop_runner import (
    LoopEvalFixture,
    LoopModeEvalRunner,
    default_loop_fixtures,
)

# Regression tolerance: ±20% wall-time deviation triggers a warning (not a hard fail).
_TIME_TOLERANCE = 0.20

_DEFAULT_SNAPSHOT_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "snapshots" / "bench"


@dataclass
class BenchFixtureResult:
    """Metrics collected for one bench fixture run."""

    fixture_name: str
    wall_time_seconds: float
    step_count: int
    patch_output_hash: str | None  # SHA-256 of pending patch text, or None
    passed: bool
    failure_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "wall_time_seconds": round(self.wall_time_seconds, 4),
            "step_count": self.step_count,
            "patch_output_hash": self.patch_output_hash,
            "passed": self.passed,
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass
class BenchRegressionReport:
    """Comparison result between a bench run and a stored baseline."""

    fixture_name: str
    baseline_time: float | None
    current_time: float
    regression: bool
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "baseline_time": self.baseline_time,
            "current_time": round(self.current_time, 4),
            "regression": self.regression,
            "message": self.message,
        }


@dataclass
class BenchRunSummary:
    """Summary of one full bench run."""

    results: list[BenchFixtureResult]
    regressions: list[BenchRegressionReport]
    snapshot_written: bool
    snapshot_dir: Path

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def has_regressions(self) -> bool:
        return any(r.regression for r in self.regressions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [r.as_dict() for r in self.results],
            "regressions": [r.as_dict() for r in self.regressions],
            "snapshot_written": self.snapshot_written,
            "snapshot_dir": str(self.snapshot_dir),
            "all_passed": self.all_passed,
            "has_regressions": self.has_regressions,
        }


def _compute_patch_hash(patch_text: str | None) -> str | None:
    if not patch_text or not patch_text.strip():
        return None
    return hashlib.sha256(patch_text.encode("utf-8")).hexdigest()


def _count_steps(fixture: LoopEvalFixture) -> int:
    """Return the number of scripted steps in the fixture (deterministic)."""
    return len(fixture.scripted_steps)


def _snapshot_path(snapshot_dir: Path, fixture_name: str) -> Path:
    safe_name = fixture_name.replace("/", "_").replace(" ", "_")
    return snapshot_dir / f"{safe_name}.json"


def _load_baseline(snapshot_dir: Path, fixture_name: str) -> dict[str, Any] | None:
    path = _snapshot_path(snapshot_dir, fixture_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_baseline(snapshot_dir: Path, result: BenchFixtureResult) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(snapshot_dir, result.fixture_name)
    path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _check_regression(
    result: BenchFixtureResult,
    baseline: dict[str, Any],
) -> BenchRegressionReport:
    baseline_time: float | None = baseline.get("wall_time_seconds")
    current_time = result.wall_time_seconds

    if baseline_time is None or baseline_time <= 0:
        return BenchRegressionReport(
            fixture_name=result.fixture_name,
            baseline_time=baseline_time,
            current_time=current_time,
            regression=False,
            message="No valid baseline time; skipping regression check.",
        )

    deviation = abs(current_time - baseline_time) / baseline_time
    regression = deviation > _TIME_TOLERANCE
    if regression:
        pct = deviation * 100
        msg = (
            f"Wall-time regression: baseline={baseline_time:.4f}s "
            f"current={current_time:.4f}s deviation={pct:.1f}% "
            f"(tolerance=±{_TIME_TOLERANCE * 100:.0f}%)"
        )
    else:
        msg = f"OK: deviation={deviation * 100:.1f}% within ±{_TIME_TOLERANCE * 100:.0f}% tolerance."

    return BenchRegressionReport(
        fixture_name=result.fixture_name,
        baseline_time=baseline_time,
        current_time=current_time,
        regression=regression,
        message=msg,
    )


class EvalBenchRunner:
    """Run all loop fixtures and collect bench metrics.

    On first run (no snapshot exists) writes a baseline to ``snapshot_dir``.
    On subsequent runs compares within ±20% tolerance.
    """

    def __init__(
        self,
        snapshot_dir: Path | None = None,
        *,
        clock: Any = None,
    ) -> None:
        self.snapshot_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR
        self._clock = clock  # injectable for tests; defaults to time.perf_counter

    def _now(self) -> float:
        if self._clock is not None:
            return self._clock()
        return time.perf_counter()

    def run_fixture(self, fixture: LoopEvalFixture) -> BenchFixtureResult:
        """Run one fixture and return timing + hash metrics."""
        runner = LoopModeEvalRunner()
        t0 = self._now()
        loop_result = runner.run_fixture(fixture)
        t1 = self._now()

        wall_time = max(t1 - t0, 0.0)
        step_count = _count_steps(fixture)
        patch_hash = _compute_patch_hash(loop_result.pending_patch_text)

        return BenchFixtureResult(
            fixture_name=fixture.name,
            wall_time_seconds=wall_time,
            step_count=step_count,
            patch_output_hash=patch_hash,
            passed=loop_result.passed,
            failure_reasons=list(loop_result.failure_reasons),
        )

    def run_all(
        self,
        fixtures: list[LoopEvalFixture] | None = None,
        *,
        update_baseline: bool = False,
    ) -> BenchRunSummary:
        """Run all fixtures; write or compare baseline snapshots."""
        if fixtures is None:
            fixtures = default_loop_fixtures()

        results: list[BenchFixtureResult] = []
        regressions: list[BenchRegressionReport] = []
        snapshot_written = False

        for fixture in fixtures:
            result = self.run_fixture(fixture)
            results.append(result)

            baseline = _load_baseline(self.snapshot_dir, fixture.name)
            if baseline is None or update_baseline:
                _write_baseline(self.snapshot_dir, result)
                snapshot_written = True
                regressions.append(BenchRegressionReport(
                    fixture_name=fixture.name,
                    baseline_time=None,
                    current_time=result.wall_time_seconds,
                    regression=False,
                    message="Baseline written (first run).",
                ))
            else:
                reg = _check_regression(result, baseline)
                regressions.append(reg)

        return BenchRunSummary(
            results=results,
            regressions=regressions,
            snapshot_written=snapshot_written,
            snapshot_dir=self.snapshot_dir,
        )


def render_bench_summary(summary: BenchRunSummary) -> str:
    """Render a human-readable bench summary for CLI output."""
    lines: list[str] = ["SafeCode Eval Bench"]
    lines.append("=" * 40)
    for r in summary.results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"[{status}] {r.fixture_name}  "
            f"steps={r.step_count}  "
            f"time={r.wall_time_seconds:.4f}s  "
            f"patch_hash={r.patch_output_hash or 'none'}"
        )
    if summary.regressions:
        lines.append("")
        lines.append("Regression checks:")
        for reg in summary.regressions:
            marker = "REGRESSION" if reg.regression else "ok"
            lines.append(f"  [{marker}] {reg.fixture_name}: {reg.message}")
    if summary.snapshot_written:
        lines.append(f"\nBaseline snapshot written to: {summary.snapshot_dir}")
    return "\n".join(lines)
