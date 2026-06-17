"""Structured repair strategy classifier for the validation loop (v6.7.1).

Classifies validation failures into typed strategies so that the repair prompt
is tailored to the failure kind rather than simply re-appending the raw tail.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path


class RepairStrategy(str, Enum):
    """Typed repair strategies matched to failure patterns."""

    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    TEST_FAILURE = "test_failure"
    TYPE_ERROR = "type_error"
    LINT_ERROR = "lint_error"
    NAME_ERROR = "name_error"
    GENERIC = "generic"


# --------------------------------------------------------------------------- #
# Pattern matchers — order matters (most specific first)
# --------------------------------------------------------------------------- #

_SYNTAX = re.compile(r"SyntaxError:|IndentationError:|TabError:", re.IGNORECASE)
_IMPORT = re.compile(r"ModuleNotFoundError:|ImportError:|No module named", re.IGNORECASE)
_NAME = re.compile(r"NameError:", re.IGNORECASE)
_TYPE = re.compile(r"TypeError:|mypy|pyright|type error", re.IGNORECASE)
_LINT = re.compile(r"ruff|flake8|pylint|E[0-9]{3,4}\b|W[0-9]{3,4}\b|C[0-9]{3,4}\b", re.IGNORECASE)
# pytest FAILED lines or assertion errors in test context
_TEST = re.compile(r"FAILED tests/|AssertionError:|assert .* ==|E\s+assert|pytest|FAILURES", re.IGNORECASE)


def classify_failure(failure_tail: str, suite_name: str = "test") -> RepairStrategy:
    """Return the most likely repair strategy for the given failure output.

    Preference order: syntax > import/name > test (when suite=test) > type > lint > generic.
    """
    if _SYNTAX.search(failure_tail):
        return RepairStrategy.SYNTAX_ERROR
    if _IMPORT.search(failure_tail):
        return RepairStrategy.IMPORT_ERROR
    if _NAME.search(failure_tail):
        return RepairStrategy.NAME_ERROR
    if suite_name == "test" and _TEST.search(failure_tail):
        return RepairStrategy.TEST_FAILURE
    if _TYPE.search(failure_tail):
        return RepairStrategy.TYPE_ERROR
    if suite_name == "lint" and _LINT.search(failure_tail):
        return RepairStrategy.LINT_ERROR
    if _LINT.search(failure_tail):
        return RepairStrategy.LINT_ERROR
    if _TEST.search(failure_tail):
        return RepairStrategy.TEST_FAILURE
    return RepairStrategy.GENERIC


# --------------------------------------------------------------------------- #
# Strategy-specific prompt builders
# --------------------------------------------------------------------------- #

_STRATEGY_INSTRUCTIONS: dict[RepairStrategy, str] = {
    RepairStrategy.SYNTAX_ERROR: (
        "REPAIR STRATEGY: syntax error.\n"
        "1. Use read_file to read the file mentioned in the traceback.\n"
        "2. Locate the line with the syntax error.\n"
        "3. Propose a minimal fix that corrects only the syntax issue.\n"
        "Do NOT change unrelated code."
    ),
    RepairStrategy.IMPORT_ERROR: (
        "REPAIR STRATEGY: import/module error.\n"
        "1. Use search_files or grep_files to find the correct module path.\n"
        "2. Verify the symbol exists in that module with grep_files.\n"
        "3. Propose a patch that corrects only the import statement.\n"
        "Do NOT guess module names — verify with search first."
    ),
    RepairStrategy.NAME_ERROR: (
        "REPAIR STRATEGY: name error (undefined name).\n"
        "1. Use grep_files to find where the name is defined.\n"
        "2. Check if the import is missing or the name is misspelled.\n"
        "3. Propose a minimal fix: add the missing import or correct the spelling.\n"
        "Do NOT change unrelated code."
    ),
    RepairStrategy.TEST_FAILURE: (
        "REPAIR STRATEGY: test assertion failure.\n"
        "1. Use read_file to read the failing test function first.\n"
        "2. Understand what behavior the test expects.\n"
        "3. Use read_file to read the implementation under test.\n"
        "4. Propose a patch that makes the implementation match the test expectation.\n"
        "Fix the implementation, not the test, unless the test is clearly wrong."
    ),
    RepairStrategy.TYPE_ERROR: (
        "REPAIR STRATEGY: type error.\n"
        "1. Use read_file to read the file and function mentioned in the error.\n"
        "2. Check the argument types and return type annotation.\n"
        "3. Propose a fix that corrects the type mismatch.\n"
        "Do NOT remove type annotations — fix them."
    ),
    RepairStrategy.LINT_ERROR: (
        "REPAIR STRATEGY: lint violation.\n"
        "1. Read each violation line in the failure output carefully.\n"
        "2. Use read_file to see the exact lines flagged.\n"
        "3. Propose a patch that fixes only the listed violations.\n"
        "Do NOT reformat unrelated code or remove needed imports."
    ),
    RepairStrategy.GENERIC: (
        "REPAIR STRATEGY: generic failure.\n"
        "1. Read the failure output carefully.\n"
        "2. Use read_file on files mentioned in the traceback.\n"
        "3. Propose the minimal change that resolves the failure."
    ),
}


def build_repair_prompt(
    strategy: RepairStrategy,
    original_goal: str,
    failure_tail: str,
    suite_name: str,
    diagnostics: str | None = None,
) -> str:
    """Construct a strategy-specific repair prompt for the validation loop."""
    instructions = _STRATEGY_INSTRUCTIONS[strategy]
    diagnostics_block = ""
    if diagnostics and diagnostics.strip():
        diagnostics_block = (
            "\n\nType diagnostics (bounded, redacted):\n"
            f"{diagnostics.strip()}"
        )
    return (
        f"{original_goal}\n\n"
        f"Validation failed in suite '{suite_name}'.\n"
        f"{instructions}\n\n"
        "Failure output (redacted):\n"
        f"{failure_tail}"
        f"{diagnostics_block}\n\n"
        "Propose a safe repair patch only. Do not apply it automatically."
    )
