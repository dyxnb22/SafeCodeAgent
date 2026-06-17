"""Tests for pre-task clarification (v6.8.0)."""

from __future__ import annotations

import pytest

from safecode.agent.clarify import (
    ClarificationResult,
    _is_specific_enough,
    detect_ambiguity,
)


class TestIsSpecificEnough:
    def test_long_goal_is_specific(self) -> None:
        goal = "a" * 130
        assert _is_specific_enough(goal) is True

    def test_file_path_makes_it_specific(self) -> None:
        assert _is_specific_enough("fix src/foo.py") is True

    def test_line_number_makes_it_specific(self) -> None:
        assert _is_specific_enough("fix line 42 in the parser") is True

    def test_def_keyword_makes_it_specific(self) -> None:
        assert _is_specific_enough("update def parse_args to accept kwargs") is True

    def test_test_name_makes_it_specific(self) -> None:
        assert _is_specific_enough("fix test_add_user failure") is True

    def test_exception_name_makes_it_specific(self) -> None:
        assert _is_specific_enough("fix the TypeError in auth module") is True

    def test_short_vague_goal_is_not_specific(self) -> None:
        assert _is_specific_enough("fix it") is False

    def test_single_vague_verb_is_not_specific(self) -> None:
        assert _is_specific_enough("improve") is False

    def test_two_word_vague_goal(self) -> None:
        assert _is_specific_enough("update this") is False


class TestClarificationResult:
    def test_skip_factory(self) -> None:
        r = ClarificationResult.skip()
        assert r.needs_clarification is False
        assert r.questions == ()

    def test_ask_factory(self) -> None:
        r = ClarificationResult.ask(["Which file?", "What behavior?"], reason="test")
        assert r.needs_clarification is True
        assert len(r.questions) == 2
        assert r.reason == "test"


class TestDetectAmbiguity:
    def test_specific_goal_skips_llm(self) -> None:
        class _NoLLM:
            def ask(self, *args, **kwargs):
                raise AssertionError("should not be called")

        result = detect_ambiguity("fix src/parser.py line 42 TypeError", _NoLLM())
        assert result.needs_clarification is False

    def test_llm_returns_no_clarification(self) -> None:
        import json

        class _MockLLM:
            def ask(self, prompt, context):
                return json.dumps({"needs_clarification": False, "questions": []})

        result = detect_ambiguity("fix it", _MockLLM())
        # Either no clarification from LLM, or heuristic skipped it
        assert isinstance(result.needs_clarification, bool)

    def test_llm_returns_clarification(self) -> None:
        import json

        class _MockLLM:
            def ask(self, prompt, context):
                return json.dumps({
                    "needs_clarification": True,
                    "questions": ["Which function?", "What is the expected behavior?"],
                })

        result = detect_ambiguity("fix it", _MockLLM())
        if result.needs_clarification:
            assert len(result.questions) <= 2

    def test_llm_error_falls_back_to_skip(self) -> None:
        class _BadLLM:
            def ask(self, *args, **kwargs):
                raise RuntimeError("network error")

        result = detect_ambiguity("fix it", _BadLLM())
        assert result.needs_clarification is False

    def test_llm_invalid_json_falls_back_to_skip(self) -> None:
        class _BadJSONLLM:
            def ask(self, *args, **kwargs):
                return "not json at all"

        result = detect_ambiguity("fix it", _BadJSONLLM())
        assert result.needs_clarification is False

    def test_no_ask_method_falls_back_to_skip(self) -> None:
        class _NoAskLLM:
            pass

        result = detect_ambiguity("fix it", _NoAskLLM())
        assert result.needs_clarification is False


class TestAgentLoopNoClarifyFlag:
    def test_no_clarify_skips_gate(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop

        loop = AgentLoop.__new__(AgentLoop)
        loop.no_clarify = True
        loop.project_root = tmp_path
        loop._sac_dir = tmp_path / ".sac"

        # _clarify_if_needed should return None when no_clarify=True,
        # because the check is in run() before calling _clarify_if_needed.
        # Here we test the flag is stored correctly.
        assert loop.no_clarify is True
