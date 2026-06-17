"""Tests for structured repair strategies (v6.7.1)."""

from __future__ import annotations

import pytest

from safecode.agent.repair import (
    RepairStrategy,
    classify_failure,
    build_repair_prompt,
)


class TestClassifyFailure:
    def test_syntax_error(self) -> None:
        tail = "  File src/foo.py, line 12\nSyntaxError: invalid syntax"
        assert classify_failure(tail) == RepairStrategy.SYNTAX_ERROR

    def test_indentation_error(self) -> None:
        tail = "IndentationError: unexpected indent (foo.py, line 5)"
        assert classify_failure(tail) == RepairStrategy.SYNTAX_ERROR

    def test_import_error(self) -> None:
        tail = "ModuleNotFoundError: No module named 'safecode.missing'"
        assert classify_failure(tail) == RepairStrategy.IMPORT_ERROR

    def test_import_error_variant(self) -> None:
        tail = "ImportError: cannot import name 'foo' from 'bar'"
        assert classify_failure(tail) == RepairStrategy.IMPORT_ERROR

    def test_name_error(self) -> None:
        tail = "NameError: name 'undefined_var' is not defined"
        assert classify_failure(tail) == RepairStrategy.NAME_ERROR

    def test_test_failure_pytest(self) -> None:
        tail = "FAILED tests/test_foo.py::test_bar - AssertionError: expected 5, got 4"
        assert classify_failure(tail, suite_name="test") == RepairStrategy.TEST_FAILURE

    def test_test_failure_assertion(self) -> None:
        tail = "E   assert result == 5\nE   where result = compute()"
        assert classify_failure(tail, suite_name="test") == RepairStrategy.TEST_FAILURE

    def test_type_error_mypy(self) -> None:
        tail = "mypy: error: Argument 1 has incompatible type"
        assert classify_failure(tail, suite_name="typecheck") == RepairStrategy.TYPE_ERROR

    def test_lint_error_ruff(self) -> None:
        tail = "ruff: E501 line too long (120 > 88)"
        assert classify_failure(tail, suite_name="lint") == RepairStrategy.LINT_ERROR

    def test_lint_error_suite_generic(self) -> None:
        tail = "E302 expected 2 blank lines, found 1"
        assert classify_failure(tail, suite_name="lint") == RepairStrategy.LINT_ERROR

    def test_generic_fallback(self) -> None:
        tail = "Some unknown error occurred during processing."
        assert classify_failure(tail) == RepairStrategy.GENERIC

    def test_syntax_takes_priority_over_test(self) -> None:
        tail = "SyntaxError: invalid syntax\nFAILED tests/test_foo.py::test_bar"
        assert classify_failure(tail, suite_name="test") == RepairStrategy.SYNTAX_ERROR

    def test_import_takes_priority_over_name(self) -> None:
        tail = "ModuleNotFoundError: No module named 'x'\nNameError: name 'y' is not defined"
        assert classify_failure(tail) == RepairStrategy.IMPORT_ERROR


class TestBuildRepairPrompt:
    def test_prompt_contains_strategy_instruction(self) -> None:
        prompt = build_repair_prompt(
            RepairStrategy.SYNTAX_ERROR,
            original_goal="fix the calculator",
            failure_tail="SyntaxError: invalid syntax",
            suite_name="test",
        )
        assert "syntax error" in prompt.lower()
        assert "read_file" in prompt
        assert "fix the calculator" in prompt
        assert "SyntaxError" in prompt

    def test_test_failure_prompt_mentions_read_file(self) -> None:
        prompt = build_repair_prompt(
            RepairStrategy.TEST_FAILURE,
            original_goal="make tests pass",
            failure_tail="FAILED tests/test_foo.py::test_bar",
            suite_name="test",
        )
        assert "read_file" in prompt
        assert "test function" in prompt.lower() or "failing test" in prompt.lower()

    def test_import_error_prompt_mentions_search(self) -> None:
        prompt = build_repair_prompt(
            RepairStrategy.IMPORT_ERROR,
            original_goal="fix imports",
            failure_tail="ModuleNotFoundError: No module named 'x'",
            suite_name="test",
        )
        assert "search_files" in prompt or "grep_files" in prompt

    def test_lint_error_prompt_focused(self) -> None:
        prompt = build_repair_prompt(
            RepairStrategy.LINT_ERROR,
            original_goal="fix lint",
            failure_tail="E501 line too long",
            suite_name="lint",
        )
        assert "lint" in prompt.lower()
        assert "Do not" in prompt

    def test_all_strategies_produce_non_empty_prompt(self) -> None:
        for strategy in RepairStrategy:
            prompt = build_repair_prompt(
                strategy, "goal", "failure output", "test"
            )
            assert len(prompt) > 20

    def test_prompt_includes_do_not_apply_automatically(self) -> None:
        prompt = build_repair_prompt(
            RepairStrategy.GENERIC, "goal", "tail", "test"
        )
        assert "automatically" in prompt.lower() or "do not apply" in prompt.lower()

    def test_prompt_includes_optional_diagnostics(self) -> None:
        prompt = build_repair_prompt(
            RepairStrategy.TYPE_ERROR,
            "goal",
            "tail",
            "typecheck",
            diagnostics="- src/foo.py:3:1 error: bad type",
        )
        assert "Type diagnostics" in prompt
        assert "src/foo.py:3:1" in prompt
