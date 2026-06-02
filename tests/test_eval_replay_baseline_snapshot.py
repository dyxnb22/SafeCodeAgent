"""Tests for v2.9.2 eval-replay-baseline-snapshot.

Snapshot deterministic typed traces for loop evals:
- tool intent types and targets
- step count and ordering
- expected_pending_patch flag
- patch_hash (derived from expected_patch_contains fragments)

Does NOT snapshot:
- LLM prose (rationale, explanation, message text)
- Timestamps
- Unstable absolute paths
- Pending patch file contents (only hash of expected fragments)

Acceptance:
- Snapshot tests are deterministic across repeated local runs.
- build_loop_eval_trace() produces byte-identical output for the same fixture.
- Stored snapshots match freshly computed traces.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.eval.loop_runner import (
    LoopEvalTrace,
    LoopStepTrace,
    build_loop_eval_trace,
    default_loop_fixtures,
)

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots" / "loop"
EXPECTED_FIXTURE_NAMES = {
    "docs-edit",
    "python-function-fix",
    "config-update-fix",
    "test-assertion-fix",
    "shell-readonly-check",
    "import-cleanup",
}


def _load_snapshot(fixture_name: str) -> dict:
    path = SNAPSHOTS_DIR / f"{fixture_name}.json"
    assert path.exists(), f"Snapshot missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── LoopEvalTrace and LoopStepTrace types ─────────────────────────────────


class TestLoopEvalTraceType:
    def test_frozen(self):
        trace = LoopEvalTrace(
            fixture_name="x",
            steps=(),
            expected_pending_patch=True,
            patch_hash="abc",
        )
        with pytest.raises((AttributeError, TypeError)):
            trace.fixture_name = "y"  # type: ignore[misc]

    def test_as_dict_keys(self):
        trace = LoopEvalTrace(
            fixture_name="x",
            steps=(
                LoopStepTrace(step_index=0, tool_intent_type="read", tool_intent_target="a.py"),
            ),
            expected_pending_patch=True,
            patch_hash="abc123",
        )
        d = trace.as_dict()
        assert set(d.keys()) == {"fixture_name", "steps", "expected_pending_patch", "patch_hash"}

    def test_as_dict_steps_serializable(self):
        step = LoopStepTrace(step_index=0, tool_intent_type="patch", tool_intent_target="b.py")
        trace = LoopEvalTrace(
            fixture_name="y",
            steps=(step,),
            expected_pending_patch=True,
            patch_hash=None,
        )
        d = trace.as_dict()
        assert isinstance(d["steps"], list)
        assert d["steps"][0]["tool_intent_type"] == "patch"


class TestLoopStepTrace:
    def test_frozen(self):
        s = LoopStepTrace(step_index=0, tool_intent_type="read", tool_intent_target="x.py")
        with pytest.raises((AttributeError, TypeError)):
            s.tool_intent_type = "patch"  # type: ignore[misc]

    def test_defaults(self):
        s = LoopStepTrace(step_index=1, tool_intent_type="read", tool_intent_target=None)
        assert not s.is_stop_for_user
        assert not s.is_first_fail_recoverable

    def test_as_dict_keys(self):
        s = LoopStepTrace(step_index=0, tool_intent_type="read", tool_intent_target="a.py")
        d = s.as_dict()
        assert set(d.keys()) == {
            "step_index", "tool_intent_type", "tool_intent_target",
            "is_stop_for_user", "is_first_fail_recoverable",
        }


# ── build_loop_eval_trace() ───────────────────────────────────────────────


class TestBuildLoopEvalTrace:
    def test_returns_loop_eval_trace(self):
        f = next(f for f in default_loop_fixtures() if f.name == "docs-edit")
        trace = build_loop_eval_trace(f)
        assert isinstance(trace, LoopEvalTrace)

    def test_fixture_name_preserved(self):
        for f in default_loop_fixtures():
            assert build_loop_eval_trace(f).fixture_name == f.name

    def test_step_count_matches_scripted_steps(self):
        for f in default_loop_fixtures():
            trace = build_loop_eval_trace(f)
            assert len(trace.steps) == len(f.scripted_steps)

    def test_stop_for_user_step_marked(self):
        f = next(f for f in default_loop_fixtures() if f.name == "shell-readonly-check")
        trace = build_loop_eval_trace(f)
        stop_steps = [s for s in trace.steps if s.is_stop_for_user]
        assert len(stop_steps) == 1
        assert stop_steps[0].tool_intent_type == "stop_for_user"
        assert stop_steps[0].tool_intent_target is None

    def test_patch_hash_present_when_expected_patch_contains_nonempty(self):
        f = next(f for f in default_loop_fixtures() if f.name == "docs-edit")
        assert f.expected_patch_contains
        trace = build_loop_eval_trace(f)
        assert trace.patch_hash is not None
        assert len(trace.patch_hash) == 64  # sha256 hex

    def test_patch_hash_none_when_no_expected_contains(self):
        f = next(f for f in default_loop_fixtures() if f.name == "shell-readonly-check")
        assert not f.expected_patch_contains
        trace = build_loop_eval_trace(f)
        assert trace.patch_hash is None

    def test_expected_pending_patch_matches_fixture(self):
        for f in default_loop_fixtures():
            trace = build_loop_eval_trace(f)
            assert trace.expected_pending_patch == f.expected_pending_patch

    def test_no_timestamps_in_trace(self):
        for f in default_loop_fixtures():
            d = build_loop_eval_trace(f).as_dict()
            assert "timestamp" not in d
            for step in d["steps"]:
                assert "timestamp" not in step

    def test_no_prose_in_trace(self):
        """Trace must not include rationale, explanation, or message text."""
        for f in default_loop_fixtures():
            d = build_loop_eval_trace(f).as_dict()
            assert "rationale" not in d
            assert "explanation" not in d
            for step in d["steps"]:
                assert "rationale" not in step
                assert "explanation" not in step


# ── Determinism across repeated runs ──────────────────────────────────────


class TestTraceDeterminism:
    def test_trace_is_identical_on_two_runs(self):
        for f in default_loop_fixtures():
            t1 = build_loop_eval_trace(f)
            t2 = build_loop_eval_trace(f)
            assert t1 == t2, f"Trace for {f.name!r} differs between runs"

    def test_trace_as_dict_is_json_stable(self):
        """JSON serialization must be byte-identical across calls."""
        for f in default_loop_fixtures():
            d1 = json.dumps(build_loop_eval_trace(f).as_dict(), sort_keys=True)
            d2 = json.dumps(build_loop_eval_trace(f).as_dict(), sort_keys=True)
            assert d1 == d2, f"JSON for {f.name!r} not stable"


# ── Stored snapshot comparison ────────────────────────────────────────────


class TestSnapshotComparison:
    def test_snapshot_files_exist_for_all_fixtures(self):
        for name in EXPECTED_FIXTURE_NAMES:
            path = SNAPSHOTS_DIR / f"{name}.json"
            assert path.exists(), f"Snapshot missing: {path}"

    @pytest.mark.parametrize("fixture_name", sorted(EXPECTED_FIXTURE_NAMES))
    def test_trace_matches_snapshot(self, fixture_name):
        fixture = next(f for f in default_loop_fixtures() if f.name == fixture_name)
        computed = build_loop_eval_trace(fixture).as_dict()
        stored = _load_snapshot(fixture_name)
        assert computed == stored, (
            f"Trace for {fixture_name!r} does not match stored snapshot.\n"
            f"Computed: {json.dumps(computed, indent=2)}\n"
            f"Stored:   {json.dumps(stored, indent=2)}"
        )

    def test_all_snapshots_have_expected_keys(self):
        for name in EXPECTED_FIXTURE_NAMES:
            d = _load_snapshot(name)
            assert "fixture_name" in d
            assert "steps" in d
            assert "expected_pending_patch" in d
            assert "patch_hash" in d

    def test_all_snapshots_have_correct_fixture_name(self):
        for name in EXPECTED_FIXTURE_NAMES:
            d = _load_snapshot(name)
            assert d["fixture_name"] == name

    def test_shell_readonly_check_snapshot_has_no_patch_hash(self):
        d = _load_snapshot("shell-readonly-check")
        assert d["patch_hash"] is None
        assert d["expected_pending_patch"] is False

    def test_patch_fixtures_have_patch_hash(self):
        patch_fixtures = EXPECTED_FIXTURE_NAMES - {"shell-readonly-check"}
        for name in patch_fixtures:
            d = _load_snapshot(name)
            assert d["patch_hash"] is not None, f"Snapshot {name!r} missing patch_hash"
            assert len(d["patch_hash"]) == 64

    def test_stop_for_user_step_in_shell_snapshot(self):
        d = _load_snapshot("shell-readonly-check")
        stop_steps = [s for s in d["steps"] if s["is_stop_for_user"]]
        assert len(stop_steps) == 1
        assert stop_steps[0]["tool_intent_type"] == "stop_for_user"

    def test_all_patch_snapshots_have_patch_step(self):
        patch_fixtures = EXPECTED_FIXTURE_NAMES - {"shell-readonly-check"}
        for name in patch_fixtures:
            d = _load_snapshot(name)
            patch_steps = [s for s in d["steps"] if s["tool_intent_type"] == "patch"]
            assert patch_steps, f"Snapshot {name!r} has no patch step"
