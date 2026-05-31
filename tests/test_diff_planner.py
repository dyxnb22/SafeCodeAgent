"""Tests for v2.1.3 diff planner: scope prediction and comparison."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from safecode.agent.planner import DiffPlan, DiffPlanner, DiffScopeResult
from safecode.patch.models import PatchBlock, PatchProposal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _proposal(*file_paths: str) -> PatchProposal:
    """Build a minimal PatchProposal touching the given file paths."""
    blocks = [
        PatchBlock(
            operation="update",
            file_path=Path(fp),
            search="old",
            replace="new",
        )
        for fp in file_paths
    ]
    return PatchProposal(
        id="patch_test",
        task="test",
        blocks=blocks,
        created_at="2026-05-31T00:00:00Z",
        model="mock",
    )


# ---------------------------------------------------------------------------
# DiffPlanner.predict — file extraction
# ---------------------------------------------------------------------------


class TestDiffPlannerPredict:
    def test_extracts_single_filename(self):
        plan = DiffPlanner().predict("Fix the bug in README.md")
        assert plan.predicted_files == ["README.md"]

    def test_extracts_path_with_directories(self):
        plan = DiffPlanner().predict("Update src/safecode/agent/loop.py with new logic")
        assert "src/safecode/agent/loop.py" in plan.predicted_files

    def test_extracts_multiple_files(self):
        plan = DiffPlanner().predict("Edit README.md and pyproject.toml for release")
        assert "README.md" in plan.predicted_files
        assert "pyproject.toml" in plan.predicted_files

    def test_deduplicates_repeated_file(self):
        plan = DiffPlanner().predict("README.md needs update, also update README.md")
        assert plan.predicted_files.count("README.md") == 1

    def test_empty_prediction_for_vague_task(self):
        plan = DiffPlanner().predict("fix the bug")
        assert plan.predicted_files == []

    def test_does_not_match_url_path_component(self):
        plan = DiffPlanner().predict("See https://example.com/guide.md for info")
        assert plan.predicted_files == []

    def test_does_not_match_http_py_url(self):
        plan = DiffPlanner().predict("check http://example.com/app.py")
        assert plan.predicted_files == []

    def test_context_hint_contributes_predictions(self):
        plan = DiffPlanner().predict("edit the config", context_hint="config.toml")
        assert "config.toml" in plan.predicted_files

    def test_task_stored_in_plan(self):
        task = "update setup.py"
        plan = DiffPlanner().predict(task)
        assert plan.task == task

    def test_various_extensions(self):
        plan = DiffPlanner().predict(
            "touch app.js styles.css main.go lib.rs service.yaml"
        )
        for fname in ["app.js", "styles.css", "main.go", "lib.rs", "service.yaml"]:
            assert fname in plan.predicted_files


# ---------------------------------------------------------------------------
# DiffPlanner.compare — scope matching
# ---------------------------------------------------------------------------


class TestDiffPlannerCompare:
    def test_match_when_actual_equals_predicted(self):
        plan = DiffPlan(task="t", predicted_files=["README.md"])
        result = DiffPlanner().compare(plan, _proposal("README.md"))

        assert result.status == "match"
        assert result.extra_files == []
        assert result.warning is None

    def test_within_scope_when_actual_is_strict_subset(self):
        plan = DiffPlan(task="t", predicted_files=["README.md", "setup.py"])
        result = DiffPlanner().compare(plan, _proposal("README.md"))

        assert result.status == "within_scope"
        assert result.extra_files == []
        assert result.warning is None

    def test_extra_files_when_patch_exceeds_prediction(self):
        plan = DiffPlan(task="t", predicted_files=["README.md"])
        result = DiffPlanner().compare(plan, _proposal("README.md", "setup.py"))

        assert result.status == "extra_files"
        assert "setup.py" in result.extra_files
        assert result.warning is not None
        assert "setup.py" in result.warning

    def test_no_prediction_when_predicted_empty(self):
        plan = DiffPlan(task="fix something", predicted_files=[])
        result = DiffPlanner().compare(plan, _proposal("README.md"))

        assert result.status == "no_prediction"
        assert result.extra_files == []
        assert result.warning is None

    def test_no_prediction_with_empty_proposal_too(self):
        plan = DiffPlan(task="t", predicted_files=[])
        empty_proposal = PatchProposal(
            id="patch_empty",
            task="t",
            blocks=[],
            created_at="2026-05-31T00:00:00Z",
            model="mock",
        )
        result = DiffPlanner().compare(plan, empty_proposal)

        assert result.status == "no_prediction"
        assert result.actual_files == []

    def test_match_when_both_predicted_and_actual_agree(self):
        plan = DiffPlan(task="t", predicted_files=["a.py", "b.md"])
        result = DiffPlanner().compare(plan, _proposal("a.py", "b.md"))

        assert result.status == "match"
        assert result.extra_files == []

    def test_extra_files_warning_contains_count(self):
        plan = DiffPlan(task="t", predicted_files=["a.py"])
        result = DiffPlanner().compare(plan, _proposal("a.py", "b.py", "c.py"))

        assert result.status == "extra_files"
        assert len(result.extra_files) == 2
        assert "2 file(s)" in result.warning

    def test_actual_files_recorded_in_result(self):
        plan = DiffPlan(task="t", predicted_files=["README.md"])
        result = DiffPlanner().compare(plan, _proposal("README.md"))

        assert result.actual_files == ["README.md"]

    def test_scope_result_contains_original_plan(self):
        plan = DiffPlan(task="my task", predicted_files=["foo.py"])
        result = DiffPlanner().compare(plan, _proposal("foo.py"))

        assert result.plan.task == "my task"


# ---------------------------------------------------------------------------
# End-to-end: predict → compare round-trip
# ---------------------------------------------------------------------------


class TestDiffPlannerRoundTrip:
    def test_predict_then_compare_match(self):
        planner = DiffPlanner()
        plan = planner.predict("Fix the bug in README.md")
        result = planner.compare(plan, _proposal("README.md"))

        assert result.status == "match"
        assert result.warning is None

    def test_predict_then_compare_extra_file(self):
        planner = DiffPlanner()
        plan = planner.predict("Update README.md")
        result = planner.compare(plan, _proposal("README.md", "CHANGELOG.md"))

        assert result.status == "extra_files"
        assert "CHANGELOG.md" in result.extra_files
        assert result.warning is not None

    def test_predict_vague_task_no_prediction(self):
        planner = DiffPlanner()
        plan = planner.predict("make it better")
        result = planner.compare(plan, _proposal("README.md"))

        assert result.status == "no_prediction"


# ---------------------------------------------------------------------------
# Orchestrator integration: scope_result attached to EditResult
# ---------------------------------------------------------------------------


class TestOrchestratorScopeResult:
    def test_edit_result_has_scope_result(self, tmp_path):
        from safecode.agent.orchestrator import AgentOrchestrator

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Demo\n\n"
            "This repository currently contains the project framework only. "
            "The implementation should be added step by step after reviewing each module boundary.\n",
            encoding="utf-8",
        )
        result = AgentOrchestrator(tmp_path).edit("演示一次安全修改")

        assert result.scope_result is not None
        assert result.scope_result.status in (
            "no_prediction", "match", "within_scope", "extra_files"
        )

    def test_edit_result_scope_status_no_prediction_for_vague_task(self, tmp_path):
        from safecode.agent.orchestrator import AgentOrchestrator

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Demo\n\n"
            "This repository currently contains the project framework only. "
            "The implementation should be added step by step after reviewing each module boundary.\n",
            encoding="utf-8",
        )
        result = AgentOrchestrator(tmp_path).edit("演示一次安全修改")

        # Chinese-only task has no file path tokens → no_prediction
        assert result.scope_result is not None
        assert result.scope_result.status == "no_prediction"

    def test_edit_result_scope_match_when_task_names_patched_file(self, tmp_path):
        from safecode.agent.orchestrator import AgentOrchestrator

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Demo\n\n"
            "This repository currently contains the project framework only. "
            "The implementation should be added step by step after reviewing each module boundary.\n",
            encoding="utf-8",
        )
        # Task explicitly names README.md; mock LLM patches README.md
        result = AgentOrchestrator(tmp_path).edit("Update README.md with new content")

        assert result.scope_result is not None
        assert result.scope_result.status in ("match", "within_scope")
        assert result.scope_result.warning is None

    def test_edit_result_extra_files_warning_when_task_names_different_file(self, tmp_path):
        from safecode.agent.orchestrator import AgentOrchestrator

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Demo\n\n"
            "This repository currently contains the project framework only. "
            "The implementation should be added step by step after reviewing each module boundary.\n",
            encoding="utf-8",
        )
        # Task names setup.py but mock LLM patches README.md → extra_files
        result = AgentOrchestrator(tmp_path).edit("Fix setup.py for packaging")

        assert result.scope_result is not None
        # mock LLM returns README.md patch, but task predicted setup.py
        assert result.scope_result.status == "extra_files"
        assert result.scope_result.warning is not None


# ---------------------------------------------------------------------------
# DiffScopeResult: Literal status enforcement
# ---------------------------------------------------------------------------


class TestDiffScopeResultLiteralStatus:
    def test_valid_statuses_are_accepted(self):
        base = {"plan": DiffPlan(task="t", predicted_files=[]), "actual_files": [], "extra_files": []}
        for status in ("no_prediction", "match", "within_scope", "extra_files"):
            result = DiffScopeResult(**base, status=status)
            assert result.status == status

    def test_invalid_status_rejected_by_pydantic(self):
        with pytest.raises(ValidationError):
            DiffScopeResult(
                plan=DiffPlan(task="t", predicted_files=[]),
                actual_files=[],
                status="unknown_value",
                extra_files=[],
            )

    def test_empty_string_status_rejected(self):
        with pytest.raises(ValidationError):
            DiffScopeResult(
                plan=DiffPlan(task="t", predicted_files=[]),
                actual_files=[],
                status="",
                extra_files=[],
            )


# ---------------------------------------------------------------------------
# DiffPlanner.compare: repeated-block deduplication
# ---------------------------------------------------------------------------


class TestDiffPlannerDeduplication:
    def test_duplicate_blocks_deduped_in_actual_files(self):
        plan = DiffPlan(task="t", predicted_files=["README.md"])
        proposal = _proposal("README.md", "README.md", "README.md")
        result = DiffPlanner().compare(plan, proposal)

        assert result.actual_files == ["README.md"]
        assert result.actual_files.count("README.md") == 1

    def test_duplicate_blocks_do_not_create_false_extra(self):
        plan = DiffPlan(task="t", predicted_files=["README.md"])
        proposal = _proposal("README.md", "README.md")
        result = DiffPlanner().compare(plan, proposal)

        assert result.status == "match"
        assert result.extra_files == []
        assert result.warning is None

    def test_duplicate_extra_file_blocks_counted_once_in_extra(self):
        plan = DiffPlan(task="t", predicted_files=["README.md"])
        proposal = _proposal("README.md", "setup.py", "setup.py")
        result = DiffPlanner().compare(plan, proposal)

        assert result.status == "extra_files"
        assert result.extra_files.count("setup.py") == 1
        assert len(result.extra_files) == 1

    def test_deduplication_preserves_insertion_order(self):
        plan = DiffPlan(task="t", predicted_files=["a.py", "b.py", "c.py"])
        proposal = _proposal("a.py", "b.py", "a.py", "c.py", "b.py")
        result = DiffPlanner().compare(plan, proposal)

        assert result.actual_files == ["a.py", "b.py", "c.py"]
        assert result.status == "match"
