"""Tests for the v5.6.0 system prompt rewrite."""

import re

import pytest

from safecode.agent.prompts import (
    PATCH_FORMAT_PROMPT_SECTION,
    SYSTEM_PROMPT,
    TOOL_USE_PROMPT_SECTION,
)

# Required section headings in SYSTEM_PROMPT
_REQUIRED_HEADINGS = [
    "## Role and constraints",
    "## Tool use strategy",
    "## How to approach a coding task",
    "## How to handle test failures",
    "## How to avoid redundant reads",
    "## When to stop and ask the user",
    "## Patch format rules",
    "## Safety rules",
]


class TestSystemPromptStructure:
    def test_non_empty(self):
        assert SYSTEM_PROMPT and len(SYSTEM_PROMPT) > 0

    def test_minimum_length(self):
        assert len(SYSTEM_PROMPT) > 500, f"SYSTEM_PROMPT too short: {len(SYSTEM_PROMPT)} chars"

    def test_all_required_headings_present(self):
        for heading in _REQUIRED_HEADINGS:
            assert heading in SYSTEM_PROMPT, f"Missing heading: {heading!r}"

    def test_tool_use_strategy_mentions_redundant_reads(self):
        assert "redundant" in SYSTEM_PROMPT.lower()

    def test_safety_section_present(self):
        assert "## Safety rules" in SYSTEM_PROMPT

    def test_safety_section_covers_env_files(self):
        assert ".env" in SYSTEM_PROMPT

    def test_safety_section_covers_secrets(self):
        assert "secret" in SYSTEM_PROMPT.lower()

    def test_no_hardcoded_version_numbers(self):
        # Version numbers in the prompt create a maintenance burden.
        # v5.6.0 in docstring is acceptable; version refs inside the prompt body are not.
        # Strip the docstring line and check the actual prompt constant.
        lines = SYSTEM_PROMPT.splitlines()
        version_pattern = re.compile(r"\bv\d+\.\d+\.\d+\b")
        for line in lines:
            assert not version_pattern.search(line), (
                f"Hard-coded version number found in SYSTEM_PROMPT: {line!r}"
            )

    def test_no_hardcoded_absolute_paths(self):
        assert "/Users/" not in SYSTEM_PROMPT
        assert "/home/" not in SYSTEM_PROMPT


class TestToolUsePromptSection:
    def test_non_empty(self):
        assert TOOL_USE_PROMPT_SECTION and len(TOOL_USE_PROMPT_SECTION) > 0

    def test_lists_key_tools(self):
        for tool in ("read_file", "edit_file", "grep_files", "run_command"):
            assert tool in TOOL_USE_PROMPT_SECTION, f"Tool missing from TOOL_USE_PROMPT_SECTION: {tool}"

    def test_importable(self):
        # Simply importing the module constant is sufficient
        assert isinstance(TOOL_USE_PROMPT_SECTION, str)

    def test_no_hardcoded_absolute_paths(self):
        assert "/Users/" not in TOOL_USE_PROMPT_SECTION


class TestPatchFormatPromptSection:
    def test_non_empty(self):
        assert PATCH_FORMAT_PROMPT_SECTION and len(PATCH_FORMAT_PROMPT_SECTION) > 0

    def test_contains_begin_patch_marker(self):
        assert "*** Begin Patch" in PATCH_FORMAT_PROMPT_SECTION

    def test_importable(self):
        assert isinstance(PATCH_FORMAT_PROMPT_SECTION, str)
