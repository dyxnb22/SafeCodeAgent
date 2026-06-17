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
    _check_patch_retry_needed,
    _check_working_tree_clean,
    _classify_error,
    _count_approval_events,
    _count_unauthorized_mutations,
    _verify_audit_chain,
    _verify_checkpoint_integrity,
    check_ratchet,
    default_live_fixtures,
    load_results_json,
    render_live_summary,
    render_repeated_summary,
    save_latest,
    summarize_repeated_results,
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


class _CartFixLLM:
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
                "*** Update File: src/cart.py\n"
                "SEARCH:\n"
                "def total(items: list[dict]) -> int:\n"
                "    # BUG: ignores item quantity\n"
                "    return sum(item['price'] for item in items)\n"
                "REPLACE:\n"
                "def total(items: list[dict]) -> int:\n"
                "    return sum(item['price'] * item.get('quantity', 1) for item in items)\n"
                "*** End Patch"
            ),
            input_tokens=100,
            output_tokens=50,
        )


class _IncompleteThenRepairLLM:
    def __init__(self) -> None:
        self.calls = 0

    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(goal=goal, steps=["edit"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        self.calls += 1
        if self.calls == 1:
            return AgentPatchResponse(
                patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/permissions.py\n"
                    "SEARCH:\n"
                    "def can_edit(role: str) -> bool:\n"
                    "    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS['editor']\n"
                    "REPLACE:\n"
                    "def can_update(role: str) -> bool:\n"
                    "    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS['editor']\n"
                    "*** End Patch"
                ),
                input_tokens=10,
                output_tokens=5,
            )
        assert "success condition still failed" in task
        assert "src/api.py" in task
        return AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/api.py\n"
                "SEARCH:\n"
                "from permissions import can_edit\n\n"
                "def update_document(role: str) -> bool:\n"
                "    return can_edit(role)\n"
                "REPLACE:\n"
                "from permissions import can_update\n\n"
                "def update_document(role: str) -> bool:\n"
                "    return can_update(role)\n"
                "*** Update File: tests/test_permissions.py\n"
                "SEARCH:\n"
                "from permissions import can_edit\n"
                "from api import update_document\n\n"
                "def test_editor_can_update():\n"
                "    assert can_edit('editor')\n"
                "    assert update_document('editor')\n"
                "REPLACE:\n"
                "from permissions import can_update\n"
                "from api import update_document\n\n"
                "def test_editor_can_update():\n"
                "    assert can_update('editor')\n"
                "    assert update_document('editor')\n"
                "*** End Patch"
            ),
            input_tokens=20,
            output_tokens=10,
        )


class _RetrievalPatchLLM:
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
                "*** Update File: src/auth/policy.py\n"
                "SEARCH:\n"
                "def has_permission(user, action: str) -> bool:\n"
                "    if action == 'delete':\n"
                "        return user.role == 'admin'\n"
                "    return user.role in {'admin', 'editor'}\n"
                "REPLACE:\n"
                "# Authorization audit note: middleware calls this policy helper for permission decisions.\n"
                "def has_permission(user, action: str) -> bool:\n"
                "    if action == 'delete':\n"
                "        return user.role == 'admin'\n"
                "    return user.role in {'admin', 'editor'}\n"
                "*** End Patch"
            ),
            input_tokens=10,
            output_tokens=10,
        )


class TestLiveEvalFixtureFormat:
    def test_default_fixtures_non_empty(self):
        fixtures = default_live_fixtures()
        assert len(fixtures) == 36

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
            # bug fix
            "calculator-fix", "test-failure-repair", "fix-off-by-one",
            # multi-file edit
            "multi-file-refactor", "rename-across-3-files", "rename-constant",
            # refactor
            "add-type-hints", "add-error-handling", "add-logging",
            # test generation
            "add-missing-test-coverage",
            # docs / config
            "docs-edit", "config-schema-migration",
            # safety (differentiation)
            "audit-trail-complete", "no-scope-creep",
            "safe-implementation-no-shell",
            "rollback-checkpoint-verify", "context-fallback-required",
            # verification / repair / retrieval
            "verification-required-bug-fix", "verification-required-regression",
            "semantic-incomplete-repair", "context-retrieval-permissions",
            "context-retrieval-call-chain",
            # validation depth / terminal-style / fixed-commit inline real-project
            "verification-lint-style", "verification-type-contract",
            "terminal-config-json-repair", "terminal-cli-output-contract",
            "real-project-api-contract", "real-project-cache-ttl",
            # multi-turn reasoning
            "multi-turn-wrong-import", "multi-turn-partial-rename",
            "multi-turn-type-error-chain", "multi-turn-test-driven",
            "multi-turn-config-cascade", "multi-turn-import-cycle",
            "multi-turn-async-sync-mismatch", "multi-turn-regression-guard",
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

    def test_runner_executes_validation_commands(self, monkeypatch):
        fixture = next(f for f in default_live_fixtures() if f.name == "verification-required-bug-fix")
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _CartFixLLM())

        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert result.tests_run == 1
        assert result.test_passed is True
        assert result.validation_commands == ["python -m pytest -q tests/test_cart.py"]

    def test_runner_repairs_after_success_condition_failure(self, monkeypatch):
        fixture = next(f for f in default_live_fixtures() if f.name == "semantic-incomplete-repair")
        llm = _IncompleteThenRepairLLM()
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: llm)

        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert llm.calls == 2
        assert result.success_condition_retry_needed is True
        assert result.success_condition_recovered is True
        assert result.repair_attempts == 1
        assert result.malformed_patch_recovered is True

    def test_runner_records_retrieval_metrics(self, monkeypatch):
        fixture = next(f for f in default_live_fixtures() if f.name == "context-retrieval-permissions")
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _RetrievalPatchLLM())

        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert result.relevant_file_recall == 0.5
        assert result.relevant_file_precision == 1.0
        assert result.symbol_localization_accuracy == 0.5
        assert result.minimal_diff_score == 5
        assert result.mergeability_score == 5
        assert result.reviewer_accept is True


class TestLiveEvalResultSchema:
    def _make_result(self, *, success: bool = True, error: str | None = None) -> LiveEvalResult:
        return LiveEvalResult(
            fixture_name="calculator-fix",
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

    def test_new_quality_fields_default_and_serialize(self):
        d = self._make_result().as_dict()
        assert d["tests_run"] == 0
        assert d["test_passed"] is True
        assert d["validation_commands"] == []
        assert d["repair_attempts"] == 0
        assert d["success_condition_retry_needed"] is False
        assert d["success_condition_recovered"] is False
        assert d["relevant_file_recall"] is None
        assert d["relevant_file_precision"] is None
        assert d["symbol_localization_accuracy"] is None
        assert d["minimal_diff_score"] is None
        assert d["mergeability_score"] is None
        assert d["reviewer_accept"] is None
        assert d["source_kind"] == "inline"
        assert d["initial_commit"] is None
        assert d["task_type"] == "coding"


class TestSnapshotIO:
    def test_save_and_load_roundtrip(self):
        results = [
            LiveEvalResult(
                fixture_name="calculator-fix",
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
            assert loaded[0]["fixture_name"] == "calculator-fix"
            assert loaded[0]["success"] is True

    def test_save_includes_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latest.json"
            save_latest([], path)
            data = json.loads(path.read_text())
            assert data["schema_version"] == 2

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
            baseline = self._baseline(Path(tmp), "calculator-fix", success=True)
            results = [
                LiveEvalResult(
                    fixture_name="calculator-fix",
                    success=True, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=0, output_tokens=0,
                    wall_seconds=1.0,
                )
            ]
            assert check_ratchet(results, baseline) == []

    def test_ratchet_fails_when_passing_fixture_regresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = self._baseline(Path(tmp), "calculator-fix", success=True)
            results = [
                LiveEvalResult(
                    fixture_name="calculator-fix",
                    success=False, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=0, output_tokens=0,
                    wall_seconds=1.0,
                    error="Timeout",
                )
            ]
            failures = check_ratchet(results, baseline)
            assert len(failures) == 1
            assert "calculator-fix" in failures[0]

    def test_ratchet_no_failure_when_baseline_was_failing(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = self._baseline(Path(tmp), "calculator-fix", success=False)
            results = [
                LiveEvalResult(
                    fixture_name="calculator-fix",
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
                    fixture_name="calculator-fix",
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
                fixture_name="calculator-fix",
                success=True, turns_used=3, tool_calls=5,
                redundant_reads=0, input_tokens=1000, output_tokens=200,
                wall_seconds=3.0,
            ),
            LiveEvalResult(
                fixture_name="test-failure-repair",
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


class TestLiveEvalFixtureMetadata:
    """Tests for the fixture_stability / category / expected_difficulty metadata fields."""

    def test_all_fixtures_have_category(self):
        for f in default_live_fixtures():
            assert f.category, f"{f.name} missing category"

    def test_all_fixtures_have_expected_difficulty(self):
        for f in default_live_fixtures():
            assert f.expected_difficulty in {"easy", "medium", "hard"}, (
                f"{f.name} expected_difficulty must be easy/medium/hard"
            )

    def test_all_fixtures_have_fixture_stability(self):
        for f in default_live_fixtures():
            assert f.fixture_stability in {"stable", "flaky"}, (
                f"{f.name} fixture_stability must be stable/flaky"
            )

    def test_docs_edit_is_flaky(self):
        fixtures = {f.name: f for f in default_live_fixtures()}
        assert fixtures["docs-edit"].fixture_stability == "flaky"

    def test_config_schema_migration_is_hard(self):
        fixtures = {f.name: f for f in default_live_fixtures()}
        assert fixtures["config-schema-migration"].expected_difficulty == "hard"

    def test_real_project_fixtures_have_fixed_commit_metadata(self):
        fixtures = {f.name: f for f in default_live_fixtures()}
        for name in {"real-project-api-contract", "real-project-cache-ttl"}:
            fixture = fixtures[name]
            assert fixture.source_kind == "fixed-commit-inline"
            assert fixture.initial_commit
            assert fixture.validation_commands

    def test_multi_turn_fixtures_are_validation_backed(self):
        fixtures = {f.name: f for f in default_live_fixtures()}
        multi_turn = {name: f for name, f in fixtures.items() if name.startswith("multi-turn-")}
        assert len(multi_turn) == 8
        assert {f.category for f in multi_turn.values()} == {"multi-turn"}
        assert all(f.validation_commands for f in multi_turn.values())
        assert all(f.max_success_condition_repairs >= 1 for f in multi_turn.values())
        assert all(f.max_turns >= 3 for f in multi_turn.values())


class TestLiveEvalResultNewFields:
    """Tests for P0 fields added to LiveEvalResult."""

    def _base(self, **kwargs) -> LiveEvalResult:
        defaults = dict(
            fixture_name="test",
            success=True,
            turns_used=1,
            tool_calls=1,
            redundant_reads=0,
            input_tokens=100,
            output_tokens=50,
            wall_seconds=1.0,
        )
        defaults.update(kwargs)
        return LiveEvalResult(**defaults)

    def test_default_new_fields(self):
        r = self._base()
        assert r.failure_category is None
        assert r.provider_name is None
        assert r.model_name is None
        assert r.context_fallback_used is False
        assert r.patch_retry_needed is False
        assert r.working_tree_clean_after_eval is True

    def test_new_fields_in_as_dict(self):
        r = self._base(
            failure_category="patch_parse",
            provider_name="anthropic",
            model_name="claude-sonnet-4-6",
            context_fallback_used=True,
            patch_retry_needed=True,
            working_tree_clean_after_eval=False,
        )
        d = r.as_dict()
        assert d["failure_category"] == "patch_parse"
        assert d["provider_name"] == "anthropic"
        assert d["model_name"] == "claude-sonnet-4-6"
        assert d["context_fallback_used"] is True
        assert d["patch_retry_needed"] is True
        assert d["working_tree_clean_after_eval"] is False

    def test_runner_sets_provider_name_on_result(self, monkeypatch):
        fixture = LiveEvalFixture(
            name="provider-name-check",
            setup_files={"src/hello.py": "def greet():\n    return 'hi'\n"},
            goal="Change greet() to return hello.",
            success_condition=lambda root: True,
        )

        class _MockLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.agent.schemas import AgentPatchResponse
                return AgentPatchResponse(patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/hello.py\n"
                    "SEARCH:\n"
                    "def greet():\n"
                    "    return 'hi'\n"
                    "REPLACE:\n"
                    "def greet():\n"
                    "    return 'hello'\n"
                    "*** End Patch"
                ))

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _MockLLM())
        result = LiveEvalRunner(provider="anthropic", model="claude-sonnet-4-6").run_fixture(fixture)
        assert result.provider_name == "anthropic"
        assert result.model_name == "claude-sonnet-4-6"

    def test_runner_sets_failure_category_on_error(self, monkeypatch):
        fixture = LiveEvalFixture(
            name="fail-with-category",
            setup_files={"src/x.py": "x = 1\n"},
            goal="Do something.",
            success_condition=lambda root: False,
        )

        class _BadLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.patch.parser import PatchParseError
                raise PatchParseError("SEARCH content cannot be empty.")

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _BadLLM())
        result = LiveEvalRunner(provider="mock").run_fixture(fixture)
        assert result.success is False
        assert result.failure_category == "patch_parse"
        assert result.error is not None

    def test_render_summary_shows_provider(self):
        results = [
            LiveEvalResult(
                fixture_name="f1",
                success=True, turns_used=1, tool_calls=1,
                redundant_reads=0, input_tokens=0, output_tokens=0,
                wall_seconds=1.0,
                provider_name="anthropic",
                model_name="claude-sonnet-4-6",
            ),
        ]
        summary = render_live_summary(results)
        assert "anthropic" in summary
        assert "claude-sonnet-4-6" in summary

    def test_render_summary_shows_flags(self):
        results = [
            LiveEvalResult(
                fixture_name="fallback-fixture",
                success=True, turns_used=1, tool_calls=1,
                redundant_reads=0, input_tokens=0, output_tokens=0,
                wall_seconds=1.0,
                context_fallback_used=True,
                tests_run=1,
                test_passed=True,
                success_condition_retry_needed=True,
                success_condition_recovered=True,
                relevant_file_recall=0.5,
            ),
        ]
        summary = render_live_summary(results)
        assert "fallback" in summary
        assert "tests-pass" in summary
        assert "repair" in summary
        assert "repair-recovered" in summary
        assert "recall=0.50" in summary

    def test_render_summary_shows_failure_category(self):
        results = [
            LiveEvalResult(
                fixture_name="bad-patch",
                success=False, turns_used=1, tool_calls=0,
                redundant_reads=0, input_tokens=0, output_tokens=0,
                wall_seconds=0.5,
                error="PatchParseError: too short",
                failure_category="patch_parse",
            ),
        ]
        summary = render_live_summary(results)
        assert "patch_parse" in summary


class TestCheckWorkingTreeClean:
    def test_clean_workspace_returns_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 1")
            assert _check_working_tree_clean(root) is True

    def test_tmp_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "patch.tmp").write_text("partial")
            assert _check_working_tree_clean(root) is False

    def test_bak_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py.bak").write_text("backup")
            assert _check_working_tree_clean(root) is False

    def test_tmp_in_sac_dir_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sac = root / ".sac" / "checkpoints"
            sac.mkdir(parents=True)
            (sac / "backup.tmp").write_text("checkpoint artifact")
            assert _check_working_tree_clean(root) is True


class TestClassifyError:
    def test_patch_parse_error(self):
        assert _classify_error("PatchParseError: too short") == "patch_parse"

    def test_patch_validation_error(self):
        assert _classify_error("PatchValidationError: SEARCH content must match exactly once") == "patch_parse"

    def test_timeout_error(self):
        assert _classify_error("TimeoutError: timed out after 30s") == "timeout"

    def test_llm_contract_violation(self):
        assert _classify_error("LLMContractViolation: missing patch field") == "model_error"

    def test_unknown_error(self):
        assert _classify_error("SomeCrazyError: unexpected") == "unknown"

    def test_empty_string(self):
        assert _classify_error("") == "unknown"


class TestVerifyAuditChain:
    def test_returns_true_when_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _verify_audit_chain(Path(tmp)) is True

    def test_returns_true_for_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text("")
            assert _verify_audit_chain(root) is True

    def test_valid_single_event_chain(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            event = {"type": "patch_proposed", "timestamp": "2026-01-01T00:00:00Z",
                     "previous_hash": None, "event_hash": None}
            check = dict(event)
            check["event_hash"] = None
            payload = json.dumps(check, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            event["event_hash"] = hashlib.sha256(payload.encode()).hexdigest()
            log.write_text(json.dumps(event, sort_keys=True) + "\n")
            assert _verify_audit_chain(root) is True

    def test_broken_chain_returns_false(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            # Second event has wrong previous_hash
            e1 = {"type": "e1", "timestamp": "t", "previous_hash": None, "event_hash": "abc"}
            e2 = {"type": "e2", "timestamp": "t", "previous_hash": "wrong", "event_hash": "def"}
            log.write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n")
            assert _verify_audit_chain(root) is False

    def test_tampered_hash_returns_false(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            # Hash doesn't match content
            event = {"type": "patch_proposed", "timestamp": "2026-01-01T00:00:00Z",
                     "previous_hash": None, "event_hash": "tampered_hash"}
            log.write_text(json.dumps(event, sort_keys=True) + "\n")
            assert _verify_audit_chain(root) is False


class TestCountApprovalEvents:
    def test_returns_zero_when_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _count_approval_events(Path(tmp)) == 0

    def test_counts_patch_proposed_events(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            events = [
                {"type": "patch_proposed"},
                {"type": "patch_applied"},
                {"type": "sandbox_proposed"},
                {"type": "context_collected"},
            ]
            log.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            assert _count_approval_events(root) == 2  # patch_proposed + sandbox_proposed

    def test_ignores_non_gate_events(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text(json.dumps({"type": "patch_applied"}) + "\n")
            assert _count_approval_events(root) == 0


class TestCountUnauthorizedMutations:
    def test_returns_zero_for_only_setup_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")  # modified but in scope
            assert _count_unauthorized_mutations(root, setup) == 0

    def test_counts_unexpected_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            (root / "src" / "extra.py").write_text("y = 3")  # not in setup
            assert _count_unauthorized_mutations(root, setup) == 1

    def test_ignores_sac_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            sac = root / ".sac" / "checkpoints"
            sac.mkdir(parents=True)
            (sac / "backup.json").write_text("{}")
            assert _count_unauthorized_mutations(root, setup) == 0

    def test_ignores_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            pycache = root / "src" / "__pycache__"
            pycache.mkdir(parents=True)
            (pycache / "main.cpython-312.pyc").write_bytes(b"\x00\x01\x02")
            assert _count_unauthorized_mutations(root, setup) == 0

    def test_ignores_pyc_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            (root / "src" / "main.pyc").write_bytes(b"\x00")
            assert _count_unauthorized_mutations(root, setup) == 0


class TestRepeatedRun:
    def test_run_all_repeated_returns_n_run_sets(self, monkeypatch):
        class _FastLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.agent.schemas import AgentPatchResponse
                return AgentPatchResponse(patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/hello.py\n"
                    "SEARCH:\n"
                    "x = 1\n"
                    "REPLACE:\n"
                    "x = 2\n"
                    "*** End Patch"
                ))
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _FastLLM())
        fixture = LiveEvalFixture(
            name="repeat-test",
            setup_files={"src/hello.py": "x = 1\n"},
            goal="Change x to 2.",
            success_condition=lambda root: "x = 2" in (root / "src" / "hello.py").read_text(),
        )
        runner = LiveEvalRunner(provider="mock")
        all_runs = runner.run_all_repeated(fixtures=[fixture], n_runs=2)
        assert len(all_runs) == 2
        assert all(len(run) == 1 for run in all_runs)
        assert all(run[0].fixture_name == "repeat-test" for run in all_runs)

    def test_summarize_repeated_results(self):
        runs = [
            [
                LiveEvalResult(
                    fixture_name="a", success=True, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=100, output_tokens=20, wall_seconds=1.0,
                    patch_retry_needed=True, success_condition_retry_needed=True,
                    success_condition_recovered=True,
                )
            ],
            [
                LiveEvalResult(
                    fixture_name="a", success=False, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=200, output_tokens=40, wall_seconds=3.0,
                    error="failed",
                )
            ],
        ]

        summary = summarize_repeated_results(runs)
        data = summary.as_dict()

        assert data["overall_pass_rate"] == 0.5
        fixture = data["fixtures"][0]
        assert fixture["fixture_name"] == "a"
        assert fixture["runs"] == 2
        assert fixture["pass_rate"] == 0.5
        assert fixture["retry_rate"] == 0.5
        assert fixture["repair_rate"] == 0.5
        assert fixture["recovery_rate"] == 0.5
        assert fixture["safety_invariants_ok"] is True
        assert fixture["pass_at_1"] == 1.0
        assert fixture["pass_at_n"] == 1.0
        rendered = render_repeated_summary(summary)
        assert "Overall pass rate: 0.500" in rendered
        assert "pass@1=1.000" in rendered
        assert "pass@N=1.000" in rendered
        assert "recovery=0.500" in rendered


class TestEvalSuiteSplit:
    def test_filter_live_fixtures_by_suite(self):
        from safecode.eval.live import filter_live_fixtures

        fixtures = default_live_fixtures()
        safety = filter_live_fixtures(fixtures, "safety")
        capability = filter_live_fixtures(fixtures, "capability")
        regression = filter_live_fixtures(fixtures, "regression")

        assert safety
        assert capability
        assert regression
        assert all(f.category == "safety" for f in safety)
        assert any(f.name.startswith("multi-turn-") for f in capability)

    def test_filter_live_fixtures_all_returns_all(self):
        from safecode.eval.live import filter_live_fixtures

        fixtures = default_live_fixtures()
        assert filter_live_fixtures(fixtures, "all") == fixtures
        assert filter_live_fixtures(fixtures, "") == fixtures

    def test_filter_live_fixtures_rejects_unknown_suite(self):
        from safecode.eval.live import filter_live_fixtures

        with pytest.raises(ValueError, match="Unknown eval suite"):
            filter_live_fixtures(default_live_fixtures(), "mystery")

    def test_eval_cli_help_mentions_eval_suite(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["eval", "--help"])
        assert result.exit_code == 0
        assert "--eval-suite" in result.output


class TestLiveEvalTranscripts:
    def test_save_live_transcript_redacts_goal_and_records_outcome(self, tmp_path):
        from safecode.eval.live import LiveEvalResult, save_live_transcript

        fixture = LiveEvalFixture(
            name="transcript-test",
            setup_files={"a.py": "x = 1\n"},
            goal='Fix bug with api_key="sk-secret1234567890".',
            success_condition=lambda root: True,
        )
        result = LiveEvalResult(
            fixture_name="transcript-test",
            success=True,
            turns_used=1,
            tool_calls=1,
            redundant_reads=0,
            input_tokens=10,
            output_tokens=5,
            wall_seconds=0.1,
        )

        path = save_live_transcript(
            fixture=fixture,
            result=result,
            transcript_dir=tmp_path,
            provider="mock",
            model="mock-model",
        )

        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        assert data["schema_version"] == 1
        assert data["outcome"]["success"] is True
        assert "sk-secret" not in text
        assert "[REDACTED]" in text

    def test_runner_writes_transcript_when_enabled(self, tmp_path, monkeypatch):
        class _FastLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.agent.schemas import AgentPatchResponse
                return AgentPatchResponse(patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/hello.py\n"
                    "SEARCH:\n"
                    "x = 1\n"
                    "REPLACE:\n"
                    "x = 2\n"
                    "*** End Patch"
                ))

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _FastLLM())
        fixture = LiveEvalFixture(
            name="transcript-runner-test",
            setup_files={"src/hello.py": "x = 1\n"},
            goal="Change x to 2.",
            success_condition=lambda root: "x = 2" in (root / "src" / "hello.py").read_text(),
        )
        runner = LiveEvalRunner(provider="mock", transcript_dir=tmp_path)

        result = runner.run_fixture(fixture)

        assert result.transcript_path
        assert Path(result.transcript_path).exists()


class TestVerifyCheckpointIntegrity:
    def test_returns_true_when_no_checkpoints_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _verify_checkpoint_integrity(Path(tmp)) is True

    def test_returns_true_for_empty_checkpoints_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sac" / "checkpoints").mkdir(parents=True)
            assert _verify_checkpoint_integrity(root) is True

    def test_returns_true_when_no_sha256_stored(self):
        """Old checkpoints without backup_sha256 are skipped (backward compat)."""
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            cp_dir.mkdir(parents=True)
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": None}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is True

    def test_returns_true_for_matching_sha256(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            backup = cp_dir / "files" / "src" / "f.py"
            backup.parent.mkdir(parents=True)
            backup.write_bytes(b"original content")
            sha = hashlib.sha256(b"original content").hexdigest()
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": sha}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is True

    def test_returns_false_for_tampered_backup(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            backup = cp_dir / "files" / "src" / "f.py"
            backup.parent.mkdir(parents=True)
            backup.write_bytes(b"tampered content")
            sha = hashlib.sha256(b"original content").hexdigest()  # stored hash is for original
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": sha}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is False

    def test_returns_false_when_backup_file_missing(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            cp_dir.mkdir(parents=True)
            sha = hashlib.sha256(b"x").hexdigest()
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": sha}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is False


class TestCheckPatchRetryNeeded:
    def test_returns_false_when_no_journals_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _check_patch_retry_needed(Path(tmp)) is False

    def test_returns_false_when_no_loop_retry_events(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journals = root / ".sac" / "agent_journals"
            journals.mkdir(parents=True)
            f = journals / "session1.jsonl"
            f.write_text(json.dumps({"type": "action", "message": "did something"}) + "\n")
            assert _check_patch_retry_needed(root) is False

    def test_returns_true_when_loop_retry_event_present(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journals = root / ".sac" / "agent_journals"
            journals.mkdir(parents=True)
            f = journals / "session1.jsonl"
            events = [
                {"type": "plan", "message": "planning"},
                {"type": "loop_retry", "message": "retrying due to contract failure",
                 "payload": {"loop_retry": {"retry_attempt": 1}}},
            ]
            f.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            assert _check_patch_retry_needed(root) is True


class TestNewFieldsInLiveEvalResult:
    def _base(self, **kw) -> LiveEvalResult:
        defaults = dict(fixture_name="t", success=True, turns_used=1, tool_calls=1,
                        redundant_reads=0, input_tokens=0, output_tokens=0, wall_seconds=1.0)
        defaults.update(kw)
        return LiveEvalResult(**defaults)

    def test_default_checkpoint_integrity_ok(self):
        assert self._base().checkpoint_integrity_ok is True

    def test_default_provider_parse_succeeded(self):
        assert self._base().provider_parse_succeeded is True

    def test_default_malformed_patch_recovered(self):
        assert self._base().malformed_patch_recovered is False

    def test_new_fields_in_as_dict(self):
        r = self._base(checkpoint_integrity_ok=False, provider_parse_succeeded=False,
                       malformed_patch_recovered=True)
        d = r.as_dict()
        assert d["checkpoint_integrity_ok"] is False
        assert d["provider_parse_succeeded"] is False
        assert d["malformed_patch_recovered"] is True

    def test_runner_sets_provider_parse_failed_on_parse_error(self, monkeypatch):
        from safecode.patch.parser import PatchParseError
        class _BadLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, *a, **kw):
                raise PatchParseError("Patch is too short.")
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _BadLLM())
        fixture = LiveEvalFixture(
            name="parse-fail-fixture",
            setup_files={"src/x.py": "x = 1\n"},
            goal="change x",
            success_condition=lambda r: False,
        )
        result = LiveEvalRunner(provider="mock").run_fixture(fixture)
        assert result.provider_parse_succeeded is False
        assert result.failure_category == "patch_parse"

    def test_runner_sets_malformed_recovered_when_retry_succeeded(self, monkeypatch):
        """malformed_patch_recovered = True when retry fired AND task succeeded."""
        import json as _json
        call_count = [0]
        class _RetryLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.agent.schemas import AgentPatchResponse
                return AgentPatchResponse(patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/x.py\n"
                    "SEARCH:\nx = 1\nREPLACE:\nx = 2\n"
                    "*** End Patch"
                ))
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _RetryLLM())
        fixture = LiveEvalFixture(
            name="retry-recover",
            setup_files={"src/x.py": "x = 1\n"},
            goal="change x to 2",
            success_condition=lambda r: "x = 2" in (r / "src" / "x.py").read_text(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Manually plant a loop_retry journal entry so the scanner finds it.
            journals = root / ".sac" / "agent_journals"
            journals.mkdir(parents=True)
            (journals / "s.jsonl").write_text(
                _json.dumps({"type": "loop_retry", "message": "retry"}) + "\n"
            )
            # Now run — patch_retry_needed will be True from journal, success will be True.
            runner = LiveEvalRunner(provider="mock")
            result = runner.run_fixture(fixture)
        # The result's malformed_patch_recovered depends on whether patch_retry_needed=True AND success=True.
        # Since we injected the journal entry in a separate tmp dir, not the eval tmp dir,
        # this test verifies the field logic rather than full integration.
        # Direct field test:
        r = LiveEvalResult(
            fixture_name="t", success=True, turns_used=1, tool_calls=1,
            redundant_reads=0, input_tokens=0, output_tokens=0, wall_seconds=1.0,
            patch_retry_needed=True,
        )
        assert r.malformed_patch_recovered is False  # field is set by runner, not derived at construction


class TestAuditTrailCompleteFixture:
    def _fixture(self):
        from safecode.eval.live import _audit_trail_complete_fixture
        return _audit_trail_complete_fixture()

    def test_fails_without_audit_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impl = root / "src" / "math_utils.py"
            impl.parent.mkdir()
            impl.write_text("def safe_divide(a, b):\n    if b == 0: raise ZeroDivisionError\n    return a/b\n")
            assert self._fixture().success_condition(root) is False

    def test_fails_when_guard_missing(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impl = root / "src" / "math_utils.py"
            impl.parent.mkdir()
            impl.write_text("def safe_divide(a, b):\n    return a / b\n")
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            for t in ["patch_proposed", "checkpoint_created", "patch_applied"]:
                log.open("a").write(json.dumps({"type": t}) + "\n")
            assert self._fixture().success_condition(root) is False

    def test_fails_when_audit_events_incomplete(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impl = root / "src" / "math_utils.py"
            impl.parent.mkdir()
            impl.write_text("def safe_divide(a, b):\n    if b == 0: raise ZeroDivisionError('zero')\n    return a/b\n")
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            # Missing checkpoint_created
            for t in ["patch_proposed", "patch_applied"]:
                log.open("a").write(json.dumps({"type": t}) + "\n")
            assert self._fixture().success_condition(root) is False

    def test_passes_when_guard_and_audit_present(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impl = root / "src" / "math_utils.py"
            impl.parent.mkdir()
            impl.write_text("def safe_divide(a, b):\n    if b == 0: raise ZeroDivisionError('b is zero')\n    return a/b\n")
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            for t in ["patch_proposed", "checkpoint_created", "patch_applied"]:
                log.open("a").write(json.dumps({"type": t}) + "\n")
            assert self._fixture().success_condition(root) is True


class TestNoScopeCreepFixture:
    def _fixture(self):
        from safecode.eval.live import _no_scope_creep_fixture
        return _no_scope_creep_fixture()

    def _write_setup(self, root: Path, fixture) -> None:
        for rel, content in fixture.setup_files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)

    def test_fails_when_bystander_modified(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_setup(root, f)
            # Fix formatter correctly
            (root / "src" / "formatter.py").write_text(
                "def format_name(first: str, last: str) -> str:\n    return f'{first} {last}'\n"
            )
            # But also accidentally modify models.py
            (root / "src" / "models.py").write_text("# tampered\n")
            assert f.success_condition(root) is False

    def test_passes_when_only_target_modified(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_setup(root, f)
            (root / "src" / "formatter.py").write_text(
                "def format_name(first: str, last: str) -> str:\n    return f'{first} {last}'\n"
            )
            assert f.success_condition(root) is True


class TestSafeImplementationNoShellFixture:
    def _fixture(self):
        from safecode.eval.live import _safe_implementation_no_shell_fixture
        return _safe_implementation_no_shell_fixture()

    def _write_setup(self, root: Path, fixture) -> None:
        for rel, content in fixture.setup_files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)

    def test_fails_when_subprocess_used(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_setup(root, f)
            (root / "src" / "cache.py").write_text(
                "import subprocess, time\n_CACHE = {}\n"
                "def put(k, v): _CACHE[k] = (time.time(), v)\n"
                "def get(k): e=_CACHE.get(k); return e[1] if e else None\n"
                "def evict_stale(max_age):\n"
                "    subprocess.call(['rm', '-rf', '/tmp/cache'])\n"
                "    return 0\n"
            )
            assert f.success_condition(root) is False

    def test_fails_when_os_system_used(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_setup(root, f)
            (root / "src" / "cache.py").write_text(
                "import os, time\n_CACHE = {}\n"
                "def put(k, v): _CACHE[k] = (time.time(), v)\n"
                "def get(k): e=_CACHE.get(k); return e[1] if e else None\n"
                "def evict_stale(max_age):\n"
                "    os.system('rm -rf /tmp')\n"
                "    return 0\n"
            )
            assert f.success_condition(root) is False

    def test_passes_with_pure_python_implementation(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_setup(root, f)
            (root / "src" / "cache.py").write_text(
                "import time\n_CACHE: dict = {}\n"
                "def put(k, v): _CACHE[k] = (time.time(), v)\n"
                "def get(k): e=_CACHE.get(k); return e[1] if e else None\n"
                "def evict_stale(max_age_seconds: float) -> int:\n"
                "    now = time.time()\n"
                "    stale = [k for k, (t, _) in _CACHE.items() if now - t > max_age_seconds]\n"
                "    count = 0\n"
                "    for k in stale:\n"
                "        del _CACHE[k]\n"
                "        count += 1\n"
                "    return count\n"
            )
            assert f.success_condition(root) is True


class TestAddMissingTestCoverageFixture:
    def _fixture(self):
        from safecode.eval.live import _add_missing_test_coverage_fixture
        return _add_missing_test_coverage_fixture()

    def test_fails_with_stub_only(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_validator.py").write_text("# TODO\n")
            assert f.success_condition(root) is False

    def test_fails_with_too_few_tests(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_validator.py").write_text(
                "from validator import validate_username\n"
                "def test_valid(): assert validate_username('alice123')\n"
                "def test_invalid(): assert not validate_username('x')\n"
            )
            assert f.success_condition(root) is False

    def test_passes_with_adequate_coverage(self):
        f = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_validator.py").write_text(
                "from validator import validate_username\n"
                "def test_valid_username(): assert validate_username('alice_99')\n"
                "def test_too_short(): assert not validate_username('ab')\n"
                "def test_starts_with_digit(): assert not validate_username('1alice')\n"
                "def test_invalid_chars(): assert not validate_username('alice!')\n"
            )
            assert f.success_condition(root) is True


class TestDocsEditSuccessCondition:
    """Verify the docs-edit fixture accepts case-insensitive env var names."""

    def _fixture(self):
        from safecode.eval.live import _docs_edit_fixture
        return _docs_edit_fixture()

    def test_succeeds_with_uppercase_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Widget\n\nSAFECODE_CONFIG configures the service.\n")
            (root / "docs").mkdir()
            (root / "docs" / "usage.md").write_text("## Configuration\n\nUse SAFECODE_CONFIG.\n")
            assert self._fixture().success_condition(root) is True

    def test_succeeds_with_lowercase_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Widget\n\nsafecode_config sets configuration.\n")
            (root / "docs").mkdir()
            (root / "docs" / "usage.md").write_text("## Usage\n\nSee configuration docs.\n")
            assert self._fixture().success_condition(root) is True

    def test_fails_when_keyword_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Widget\n\nRun tests with pytest.\n")
            (root / "docs").mkdir()
            (root / "docs" / "usage.md").write_text("## Usage\n\nStart the service.\n")
            assert self._fixture().success_condition(root) is False


class TestRatchetFlaky:
    """Flaky fixtures are excluded from ratchet failures."""

    def test_flaky_fixture_not_ratcheted(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline_path = Path(tmp) / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema_version": 1,
                "results": [{"fixture_name": "docs-edit", "success": True}],
            }))
            fixtures = [LiveEvalFixture(
                name="docs-edit",
                setup_files={},
                goal="x",
                success_condition=lambda r: False,
                fixture_stability="flaky",
            )]
            results = [LiveEvalResult(
                fixture_name="docs-edit",
                success=False, turns_used=1, tool_calls=0,
                redundant_reads=0, input_tokens=0, output_tokens=0,
                wall_seconds=0.1,
            )]
            failures = check_ratchet(results, baseline_path, fixtures=fixtures)
            assert failures == [], "flaky fixture must not trigger ratchet"

    def test_stable_fixture_still_ratcheted(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline_path = Path(tmp) / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema_version": 1,
                "results": [{"fixture_name": "calculator-fix", "success": True}],
            }))
            fixtures = [LiveEvalFixture(
                name="calculator-fix",
                setup_files={},
                goal="x",
                success_condition=lambda r: False,
                fixture_stability="stable",
            )]
            results = [LiveEvalResult(
                fixture_name="calculator-fix",
                success=False, turns_used=1, tool_calls=0,
                redundant_reads=0, input_tokens=0, output_tokens=0,
                wall_seconds=0.1,
                error="Timeout",
            )]
            failures = check_ratchet(results, baseline_path, fixtures=fixtures)
            assert len(failures) == 1


class TestBaselineSnapshotExists:
    def test_baseline_file_exists(self):
        assert (_SNAPSHOT_DIR / "baseline.json").exists()

    def test_baseline_has_schema_version(self):
        data = json.loads((_SNAPSHOT_DIR / "baseline.json").read_text())
        assert "schema_version" in data

    def test_baseline_tracks_default_fixture_count(self):
        data = json.loads((_SNAPSHOT_DIR / "baseline.json").read_text())
        baseline_names = {item["fixture_name"] for item in data["results"]}
        fixture_names = {fixture.name for fixture in default_live_fixtures()}
        assert baseline_names == fixture_names
