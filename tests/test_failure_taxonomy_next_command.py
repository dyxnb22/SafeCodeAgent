"""Tests for v4.16.2 error-message rewrite and sac why."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.core.failure_category import (
    FailureCategory,
    all_failure_categories,
    suggested_command_for_category,
)

runner = CliRunner()


class TestFailureCategoryNextCommand:
    def test_every_category_has_suggested_command(self) -> None:
        for cat_val in all_failure_categories():
            cmd = suggested_command_for_category(cat_val)
            assert cmd, f"Category {cat_val} should have a suggested command"
            assert isinstance(cmd, str)
            assert len(cmd) > 0

    def test_next_command_property(self) -> None:
        cat = FailureCategory.PROVIDER_AUTH_FAILED
        assert "sac" in cat.next_command

    def test_unknown_fallback(self) -> None:
        cmd = suggested_command_for_category("nonexistent_category")
        assert "sac" in cmd


class TestSacWhy:
    def test_why_shows_problem_and_next(self) -> None:
        result = runner.invoke(app, ["why"], catch_exceptions=False)
        assert result.exit_code == 0
        # Either "No recent failure" (clean env) or the standard format
        assert ("No recent failure" in result.stdout or
                "Problem:" in result.stdout)
        if "Problem:" in result.stdout:
            assert "Next:" in result.stdout
            assert "Category:" in result.stdout
