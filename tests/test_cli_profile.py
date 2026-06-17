"""Tests for sac profile CLI commands (v4.2.0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.project.profile import (
    ProjectProfile,
    apply_user_override,
    load_profile,
    save_profile,
    ProfileCommand,
)

runner = CliRunner()


def _invoke(*args, cwd: Path | None = None):
    """Run the CLI with the given args, optionally overriding the working directory."""
    if cwd:
        import os
        old = os.getcwd()
        try:
            os.chdir(cwd)
            return runner.invoke(app, list(args))
        finally:
            os.chdir(old)
    return runner.invoke(app, list(args))


class TestProfileDetect:
    def test_detect_python_project(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        result = _invoke("profile", "detect", cwd=tmp_path)
        assert result.exit_code == 0
        assert "detected" in result.output.lower() or "profile" in result.output.lower()
        profile = load_profile(tmp_path)
        assert profile is not None
        assert profile.test is not None

    def test_detect_go_project(self, tmp_path):
        (tmp_path / "go.mod").touch()
        result = _invoke("profile", "detect", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile is not None
        assert profile.test is not None
        assert "go" in profile.test.command

    def test_detect_rust_project(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        result = _invoke("profile", "detect", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile is not None
        assert "cargo" in profile.test.command

    def test_detect_json_output(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        result = _invoke("profile", "detect", "--json", cwd=tmp_path)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "profile detect"
        assert data["status"] == "success"
        assert "test" in data["data"]

    def test_detect_json_deterministic(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        result1 = _invoke("profile", "detect", "--json", cwd=tmp_path)
        result2 = _invoke("profile", "detect", "--json", cwd=tmp_path)
        assert result1.output == result2.output

    def test_detect_persists_to_disk(self, tmp_path):
        (tmp_path / "go.mod").touch()
        _invoke("profile", "detect", cwd=tmp_path)
        assert (tmp_path / ".sac" / "project_profile.json").exists()

    def test_detect_user_override_preserved(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        # Set a user override first
        apply_user_override(tmp_path, "test", ("my-custom-test",))
        # Re-detect
        result = _invoke("profile", "detect", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile is not None
        assert profile.test is not None
        assert profile.test.command == ("my-custom-test",)
        assert profile.test.source == "user"


class TestProfileShow:
    def test_show_no_profile(self, tmp_path):
        result = _invoke("profile", "show", cwd=tmp_path)
        assert result.exit_code == 1

    def test_show_existing_profile(self, tmp_path):
        (tmp_path / "go.mod").touch()
        _invoke("profile", "detect", cwd=tmp_path)
        result = _invoke("profile", "show", cwd=tmp_path)
        assert result.exit_code == 0

    def test_show_json_shape(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        _invoke("profile", "detect", cwd=tmp_path)
        result = _invoke("profile", "show", "--json", cwd=tmp_path)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["command"] == "profile show"
        profile_data = data["data"]
        assert "test" in profile_data
        assert "lint" in profile_data
        assert "typecheck" in profile_data
        assert "build" in profile_data
        assert "user_overrides" in profile_data
        assert "payload_version" in profile_data

    def test_show_json_no_profile_error(self, tmp_path):
        result = _invoke("profile", "show", "--json", cwd=tmp_path)
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_show_json_deterministic(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        _invoke("profile", "detect", cwd=tmp_path)
        r1 = _invoke("profile", "show", "--json", cwd=tmp_path)
        r2 = _invoke("profile", "show", "--json", cwd=tmp_path)
        assert r1.output == r2.output


class TestProfileSet:
    def test_set_test_command(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest -q", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile is not None
        assert profile.test is not None
        assert profile.test.command == ("pytest", "-q")
        assert profile.test.source == "user"
        assert "test" in profile.user_overrides

    def test_set_lint_command(self, tmp_path):
        result = _invoke("profile", "set", "lint", "ruff check .", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile is not None
        assert profile.lint is not None
        assert profile.lint.command == ("ruff", "check", ".")

    def test_set_typecheck_command(self, tmp_path):
        result = _invoke("profile", "set", "typecheck", "mypy src/", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile.typecheck is not None
        assert profile.typecheck.command == ("mypy", "src/")

    def test_set_build_command(self, tmp_path):
        result = _invoke("profile", "set", "build", "cargo build --release", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile.build is not None
        assert profile.build.command == ("cargo", "build", "--release")

    def test_set_invalid_kind(self, tmp_path):
        result = _invoke("profile", "set", "compile", "make", cwd=tmp_path)
        assert result.exit_code != 0

    def test_set_json_output(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest", "--json", cwd=tmp_path)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["kind"] == "test"

    def test_metachar_semicolon_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest; rm -rf /", cwd=tmp_path)
        assert result.exit_code != 0

    def test_metachar_pipe_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest | cat", cwd=tmp_path)
        assert result.exit_code != 0

    def test_metachar_ampersand_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest & bg", cwd=tmp_path)
        assert result.exit_code != 0

    def test_metachar_dollar_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest $SOME_VAR", cwd=tmp_path)
        assert result.exit_code != 0

    def test_metachar_backtick_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest `date`", cwd=tmp_path)
        assert result.exit_code != 0

    def test_metachar_newline_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest\nrm -rf /", cwd=tmp_path)
        assert result.exit_code != 0

    def test_empty_command_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "   ", cwd=tmp_path)
        assert result.exit_code != 0

    def test_set_json_metachar_rejected(self, tmp_path):
        result = _invoke("profile", "set", "test", "pytest; bad", "--json", cwd=tmp_path)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_set_invalid_kind_json(self, tmp_path):
        result = _invoke("profile", "set", "unknown", "cmd", "--json", cwd=tmp_path)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"


class TestProfileClear:
    def test_clear_existing_override(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        apply_user_override(tmp_path, "test", ("my-test",))
        result = _invoke("profile", "clear", "test", cwd=tmp_path)
        assert result.exit_code == 0
        profile = load_profile(tmp_path)
        assert profile is not None
        assert "test" not in profile.user_overrides

    def test_clear_invalid_kind(self, tmp_path):
        result = _invoke("profile", "clear", "badkind", cwd=tmp_path)
        assert result.exit_code != 0

    def test_clear_json_output(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        apply_user_override(tmp_path, "test", ("my-test",))
        result = _invoke("profile", "clear", "test", "--json", cwd=tmp_path)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["kind"] == "test"

    def test_clear_without_existing_override(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        _invoke("profile", "detect", cwd=tmp_path)
        result = _invoke("profile", "clear", "lint", cwd=tmp_path)
        assert result.exit_code == 0


class TestProfileJSONShape:
    def test_json_keys_sorted(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        _invoke("profile", "detect", cwd=tmp_path)
        result = _invoke("profile", "show", "--json", cwd=tmp_path)
        raw = result.output
        data = json.loads(raw)
        # Verify top-level keys sorted
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_user_overrides_sorted_list(self, tmp_path):
        apply_user_override(tmp_path, "test", ("t",))
        apply_user_override(tmp_path, "lint", ("l",))
        result = _invoke("profile", "show", "--json", cwd=tmp_path)
        data = json.loads(result.output)
        overrides = data["data"]["user_overrides"]
        assert overrides == sorted(overrides)

    def test_detect_json_has_missing_dependency_field(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        result = _invoke("profile", "detect", "--json", cwd=tmp_path)
        data = json.loads(result.output)
        test_entry = data["data"]["test"]
        assert "missing_dependency" in test_entry
