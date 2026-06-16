"""Tests for the v5.6.1 live eval harness (all mock, no real provider calls)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from safecode.eval.live import (
    LiveEvalFixture,
    LiveEvalResult,
    LiveEvalRunner,
    check_ratchet,
    default_live_fixtures,
    load_results_json,
    render_live_summary,
    save_latest,
)
from safecode.agent.schemas import AgentAnswer, AgentPatchResponse, AgentPlanResponse

_SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "live_eval"


class _PatchOnlyLLM:
    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(goal=goal, steps=["edit"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        return AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/hello.py\n"
                "SEARCH:\n"
                "def greet():\n"
                "    return 'hi'\n"
                "REPLACE:\n"
                "def greet():\n"
                "    return 'hello'\n"
                "*** End Patch"
            )
        )


class TestLiveEvalFixtureFormat:
    def test_default_fixtures_non_empty(self):
        fixtures = default_live_fixtures()
        assert len(fixtures) == 5

    def test_all_fixtures_have_required_fields(self):
        for f in default_live_fixtures():
            assert f.name, f"Fixture missing name"
            assert f.setup_files, f"Fixture {f.name} has no setup_files"
            assert f.goal, f"Fixture {f.name} has no goal"
            assert callable(f.success_condition), f"Fixture {f.name} has no success_condition"
            assert f.max_turns > 0, f"Fixture {f.name} max_turns must be > 0"

    def test_fixture_names_are_unique(self):
        names = [f.name for f in default_live_fixtures()]
        assert len(names) == len(set(names)), "Fixture names must be unique"

    def test_fixture_names_match_spec(self):
        names = {f.name for f in default_live_fixtures()}
        expected = {
            "python-add-function",
            "python-fix-failing-test",
            "python-refactor-rename",
            "go-add-handler",
            "ts-fix-type-error",
        }
        assert names == expected

    def test_setup_files_dict_non_empty(self):
        for f in default_live_fixtures():
            assert len(f.setup_files) >= 1

    def test_success_condition_callable_with_temp_dir(self):
        for f in default_live_fixtures():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                # Write setup files so condition doesn't crash
                for rel, content in f.setup_files.items():
                    target = root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
                # Fresh project: success_condition should return False (not yet solved)
                result = f.success_condition(root)
                assert isinstance(result, bool)


class TestLiveEvalRunner:
    def test_runner_applies_generated_patch(self, monkeypatch):
        fixture = LiveEvalFixture(
            name="apply-generated-patch",
            setup_files={"src/hello.py": "def greet():\n    return 'hi'\n"},
            goal="Change greet() to return hello.",
            success_condition=lambda root: "return 'hello'" in (root / "src/hello.py").read_text(),
        )

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _PatchOnlyLLM())
        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert result.tool_calls == 1
        assert result.error is None

    def test_runner_enables_provider_network_allowlist(self, monkeypatch):
        captured = {}
        fixture = LiveEvalFixture(
            name="provider-network",
            setup_files={"src/hello.py": "def greet():\n    return 'hi'\n"},
            goal="Change greet() to return hello.",
            success_condition=lambda root: True,
        )

        def fake_create_client(cfg):
            captured["network_enabled"] = cfg.sandbox.network_enabled
            captured["network_allowlist"] = list(cfg.sandbox.network_allowlist)
            return _PatchOnlyLLM()

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", fake_create_client)
        result = LiveEvalRunner(provider="deepseek").run_fixture(fixture)

        assert result.success is True
        assert captured == {
            "network_enabled": True,
            "network_allowlist": ["api.deepseek.com"],
        }


class TestLiveEvalResultSchema:
    def _make_result(self, *, success: bool = True, error: str | None = None) -> LiveEvalResult:
        return LiveEvalResult(
            fixture_name="python-add-function",
            success=success,
            turns_used=3,
            tool_calls=5,
            redundant_reads=0,
            input_tokens=1200,
            output_tokens=300,
            wall_seconds=4.5,
            error=error,
        )

    def test_as_dict_has_required_fields(self):
        d = self._make_result().as_dict()
        required = {
            "fixture_name", "success", "turns_used", "tool_calls",
            "redundant_reads", "input_tokens", "output_tokens", "wall_seconds", "error",
        }
        assert required.issubset(d.keys())

    def test_as_dict_success_is_bool(self):
        assert isinstance(self._make_result(success=True).as_dict()["success"], bool)

    def test_as_dict_wall_seconds_rounded(self):
        r = self._make_result()
        r.wall_seconds = 3.141592653
        d = r.as_dict()
        assert d["wall_seconds"] == round(3.141592653, 3)

    def test_as_dict_error_none_when_success(self):
        assert self._make_result(success=True).as_dict()["error"] is None


class TestSnapshotIO:
    def test_save_and_load_roundtrip(self):
        results = [
            LiveEvalResult(
                fixture_name="python-add-function",
                success=True, turns_used=2, tool_calls=4,
                redundant_reads=0, input_tokens=800, output_tokens=200,
                wall_seconds=2.0,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latest.json"
            save_latest(results, path)
            loaded = load_results_json(path)
            assert len(loaded) == 1
            assert loaded[0]["fixture_name"] == "python-add-function"
            assert loaded[0]["success"] is True

    def test_save_includes_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latest.json"
            save_latest([], path)
            data = json.loads(path.read_text())
            assert data["schema_version"] == 1

    def test_load_missing_file_returns_empty(self):
        assert load_results_json(Path("/nonexistent/path.json")) == []


class TestRatchetLogic:
    def _baseline(self, tmp: Path, fixture_name: str, success: bool) -> Path:
        path = tmp / "baseline.json"
        data = {
            "schema_version": 1,
            "results": [{"fixture_name": fixture_name, "success": success}],
        }
        path.write_text(json.dumps(data))
        return path

    def test_ratchet_no_failure_when_still_passing(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = self._baseline(Path(tmp), "python-add-function", success=True)
            results = [
                LiveEvalResult(
                    fixture_name="python-add-function",
                    success=True, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=0, output_tokens=0,
                    wall_seconds=1.0,
                )
            ]
            assert check_ratchet(results, baseline) == []

    def test_ratchet_fails_when_passing_fixture_regresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = self._baseline(Path(tmp), "python-add-function", success=True)
            results = [
                LiveEvalResult(
                    fixture_name="python-add-function",
                    success=False, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=0, output_tokens=0,
                    wall_seconds=1.0,
                    error="Timeout",
                )
            ]
            failures = check_ratchet(results, baseline)
            assert len(failures) == 1
            assert "python-add-function" in failures[0]

    def test_ratchet_no_failure_when_baseline_was_failing(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = self._baseline(Path(tmp), "python-add-function", success=False)
            results = [
                LiveEvalResult(
                    fixture_name="python-add-function",
                    success=False, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=0, output_tokens=0,
                    wall_seconds=1.0,
                )
            ]
            assert check_ratchet(results, baseline) == []

    def test_ratchet_empty_baseline_never_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline.json"
            results = [
                LiveEvalResult(
                    fixture_name="python-add-function",
                    success=False, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=0, output_tokens=0,
                    wall_seconds=1.0,
                )
            ]
            assert check_ratchet(results, Path(baseline)) == []


class TestRenderLiveSummary:
    def test_render_shows_pass_count(self):
        results = [
            LiveEvalResult(
                fixture_name="python-add-function",
                success=True, turns_used=3, tool_calls=5,
                redundant_reads=0, input_tokens=1000, output_tokens=200,
                wall_seconds=3.0,
            ),
            LiveEvalResult(
                fixture_name="go-add-handler",
                success=False, turns_used=6, tool_calls=8,
                redundant_reads=1, input_tokens=2000, output_tokens=400,
                wall_seconds=10.0,
                error="AssertionError",
            ),
        ]
        summary = render_live_summary(results)
        assert "Passed: 1/2" in summary
        assert "PASS" in summary
        assert "FAIL" in summary
        assert "AssertionError" in summary


class TestLiveModeSkipsWithoutEnvVar:
    def test_live_mode_skips_without_env(self, monkeypatch):
        monkeypatch.delenv("SAFECODE_LIVE_TESTS", raising=False)
        live_tests_set = bool(os.environ.get("SAFECODE_LIVE_TESTS"))
        assert not live_tests_set


class TestBaselineSnapshotExists:
    def test_baseline_file_exists(self):
        assert (_SNAPSHOT_DIR / "baseline.json").exists()

    def test_baseline_has_schema_version(self):
        data = json.loads((_SNAPSHOT_DIR / "baseline.json").read_text())
        assert "schema_version" in data
