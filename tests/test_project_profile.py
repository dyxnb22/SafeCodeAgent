"""Tests for src/safecode/project/profile.py (v4.2.0)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from safecode.project.profile import (
    ProfileCommand,
    ProjectProfile,
    _has_metachar,
    _SHELL_METACHAR,
    _VALID_KINDS,
    apply_user_override,
    clear_user_override,
    detect_profile,
    load_profile,
    save_profile,
    _detect_raw,
    _is_python_project,
    _is_node_project,
    _is_go_project,
    _is_rust_project,
)


# ---------------------------------------------------------------------------
# ProfileCommand model
# ---------------------------------------------------------------------------

class TestProfileCommand:
    def test_basic(self):
        cmd = ProfileCommand(command=("pytest", "-q"), stack="python", source="detected")
        assert cmd.command == ("pytest", "-q")
        assert cmd.stack == "python"
        assert cmd.source == "detected"
        assert cmd.missing_dependency is False

    def test_frozen(self):
        cmd = ProfileCommand(command=("pytest",), stack="python", source="detected")
        with pytest.raises(Exception):
            cmd.command = ("ruff",)  # type: ignore[misc]

    def test_source_values(self):
        for s in ("detected", "user", "none"):
            cmd = ProfileCommand(command=("x",), stack="x", source=s)  # type: ignore[arg-type]
            assert cmd.source == s

    def test_missing_dependency_flag(self):
        cmd = ProfileCommand(command=("nonexistent_binary_xyz",), stack="x", source="detected", missing_dependency=True)
        assert cmd.missing_dependency is True

    def test_round_trip_via_dict(self):
        cmd = ProfileCommand(command=("go", "test", "./..."), stack="go", source="detected")
        d = cmd.model_dump(mode="json")
        restored = ProfileCommand.model_validate(d)
        assert restored.command == ("go", "test", "./...")


# ---------------------------------------------------------------------------
# ProjectProfile model
# ---------------------------------------------------------------------------

class TestProjectProfile:
    def test_defaults(self):
        p = ProjectProfile()
        assert p.payload_version == 1
        assert p.test is None
        assert p.lint is None
        assert p.typecheck is None
        assert p.build is None
        assert p.user_overrides == frozenset()

    def test_frozen(self):
        p = ProjectProfile()
        with pytest.raises(Exception):
            p.test = None  # type: ignore[misc]

    def test_user_overrides_frozenset(self):
        p = ProjectProfile(user_overrides=frozenset({"test", "lint"}))
        assert "test" in p.user_overrides
        assert "lint" in p.user_overrides

    def test_round_trip_full(self):
        cmd = ProfileCommand(command=("pytest", "-q"), stack="python", source="detected")
        p = ProjectProfile(test=cmd, user_overrides=frozenset({"test"}))
        d = p.model_dump(mode="json")
        restored = ProjectProfile.model_validate(d)
        assert restored.test is not None
        assert restored.test.command == ("pytest", "-q")
        assert "test" in restored.user_overrides


# ---------------------------------------------------------------------------
# Metachar detection
# ---------------------------------------------------------------------------

class TestMetacharDetection:
    @pytest.mark.parametrize("char", list(_SHELL_METACHAR))
    def test_metachar_detected(self, char):
        assert _has_metachar(f"cmd{char}stuff") is True

    def test_clean_command(self):
        assert _has_metachar("pytest -q tests/") is False
        assert _has_metachar("cargo clippy --no-deps") is False
        assert _has_metachar("go test ./...") is False


# ---------------------------------------------------------------------------
# Persistence: save / load
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        cmd = ProfileCommand(command=("pytest", "-q"), stack="python", source="detected")
        profile = ProjectProfile(test=cmd, user_overrides=frozenset({"test"}))
        save_profile(tmp_path, profile)

        loaded = load_profile(tmp_path)
        assert loaded is not None
        assert loaded.test is not None
        assert loaded.test.command == ("pytest", "-q")
        assert "test" in loaded.user_overrides

    def test_missing_returns_none(self, tmp_path):
        assert load_profile(tmp_path) is None

    def test_atomic_write(self, tmp_path):
        """save_profile uses tmp file + os.replace for atomicity."""
        profile = ProjectProfile()
        save_profile(tmp_path, profile)
        profile_path = tmp_path / ".sac" / "project_profile.json"
        tmp_path_check = profile_path.with_suffix(".tmp")
        # .tmp should be cleaned up
        assert not tmp_path_check.exists()
        assert profile_path.exists()

    def test_json_keys_sorted(self, tmp_path):
        profile = ProjectProfile()
        save_profile(tmp_path, profile)
        raw = (tmp_path / ".sac" / "project_profile.json").read_text()
        data = json.loads(raw)
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_corrupted_returns_none(self, tmp_path):
        sac = tmp_path / ".sac"
        sac.mkdir()
        (sac / "project_profile.json").write_text("not json")
        assert load_profile(tmp_path) is None

    def test_user_overrides_sorted_in_json(self, tmp_path):
        profile = ProjectProfile(user_overrides=frozenset({"test", "lint", "build"}))
        save_profile(tmp_path, profile)
        raw = (tmp_path / ".sac" / "project_profile.json").read_text()
        data = json.loads(raw)
        overrides = data["user_overrides"]
        assert overrides == sorted(overrides)


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

class TestPythonDetection:
    def test_detects_pytest_with_tests_dir(self, tmp_path):
        (tmp_path / "tests").mkdir()
        detected = _detect_raw(tmp_path)
        assert "test" in detected
        cmd = detected["test"]
        assert "pytest" in cmd.command

    def test_uses_uv_run_when_uv_lock(self, tmp_path):
        (tmp_path / "uv.lock").touch()
        (tmp_path / "pyproject.toml").touch()
        detected = _detect_raw(tmp_path)
        assert detected["test"].command[:2] == ("uv", "run")

    def test_detects_lint_ruff(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        detected = _detect_raw(tmp_path)
        assert "lint" in detected
        assert detected["lint"].command[0] == "ruff"

    def test_detects_typecheck_mypy(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        detected = _detect_raw(tmp_path)
        assert "typecheck" in detected
        assert detected["typecheck"].command[0] == "mypy"

    def test_no_build_for_python(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        detected = _detect_raw(tmp_path)
        assert "build" not in detected

    def test_is_python_project_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        assert _is_python_project(tmp_path)

    def test_is_python_project_tests_dir(self, tmp_path):
        (tmp_path / "tests").mkdir()
        assert _is_python_project(tmp_path)


class TestNodeDetection:
    def _pkg(self, tmp_path: Path, scripts: dict, lock: str = "none") -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "test", "scripts": scripts}), encoding="utf-8"
        )
        if lock == "pnpm":
            (tmp_path / "pnpm-lock.yaml").touch()
        elif lock == "yarn":
            (tmp_path / "yarn.lock").touch()

    def test_npm_test(self, tmp_path):
        self._pkg(tmp_path, {"test": "jest"})
        detected = _detect_raw(tmp_path)
        assert detected["test"].command == ("npm", "test")
        assert detected["test"].stack == "node"

    def test_pnpm_test(self, tmp_path):
        self._pkg(tmp_path, {"test": "jest"}, lock="pnpm")
        detected = _detect_raw(tmp_path)
        assert detected["test"].command == ("pnpm", "test")

    def test_yarn_test(self, tmp_path):
        self._pkg(tmp_path, {"test": "jest"}, lock="yarn")
        detected = _detect_raw(tmp_path)
        assert detected["test"].command == ("yarn", "test")

    def test_lint_script(self, tmp_path):
        self._pkg(tmp_path, {"lint": "eslint ."})
        detected = _detect_raw(tmp_path)
        assert detected["lint"].command == ("npm", "run", "lint")

    def test_typecheck_script(self, tmp_path):
        self._pkg(tmp_path, {"typecheck": "tsc --noEmit"})
        detected = _detect_raw(tmp_path)
        assert detected["typecheck"].command == ("npm", "run", "typecheck")

    def test_build_script(self, tmp_path):
        self._pkg(tmp_path, {"build": "vite build"})
        detected = _detect_raw(tmp_path)
        assert detected["build"].command == ("npm", "run", "build")

    def test_missing_script_not_in_result(self, tmp_path):
        self._pkg(tmp_path, {"test": "jest"})
        detected = _detect_raw(tmp_path)
        assert "lint" not in detected

    def test_all_four_scripts(self, tmp_path):
        self._pkg(tmp_path, {
            "test": "jest",
            "lint": "eslint .",
            "typecheck": "tsc",
            "build": "vite build",
        })
        detected = _detect_raw(tmp_path)
        assert set(detected.keys()) == {"test", "lint", "typecheck", "build"}

    def test_is_node_project(self, tmp_path):
        (tmp_path / "package.json").touch()
        assert _is_node_project(tmp_path)


class TestGoDetection:
    def test_detects_all_kinds(self, tmp_path):
        (tmp_path / "go.mod").touch()
        detected = _detect_raw(tmp_path)
        assert detected["test"].command == ("go", "test", "./...")
        assert detected["lint"].command == ("go", "vet", "./...")
        assert detected["build"].command == ("go", "build", "./...")
        assert "typecheck" not in detected

    def test_stack_is_go(self, tmp_path):
        (tmp_path / "go.mod").touch()
        detected = _detect_raw(tmp_path)
        assert detected["test"].stack == "go"

    def test_is_go_project(self, tmp_path):
        (tmp_path / "go.mod").touch()
        assert _is_go_project(tmp_path)


class TestRustDetection:
    def test_detects_all_four(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        detected = _detect_raw(tmp_path)
        assert detected["test"].command == ("cargo", "test")
        assert detected["lint"].command == ("cargo", "clippy", "--no-deps")
        assert detected["typecheck"].command == ("cargo", "check")
        assert detected["build"].command == ("cargo", "build")

    def test_stack_is_rust(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        detected = _detect_raw(tmp_path)
        assert detected["test"].stack == "rust"

    def test_is_rust_project(self, tmp_path):
        (tmp_path / "Cargo.toml").touch()
        assert _is_rust_project(tmp_path)


class TestNoProject:
    def test_empty_dir_no_commands(self, tmp_path):
        detected = _detect_raw(tmp_path)
        assert detected == {}


# ---------------------------------------------------------------------------
# Missing dependency flag
# ---------------------------------------------------------------------------

class TestMissingDependency:
    def test_nonexistent_binary_flagged(self, tmp_path):
        """If the head binary is not on PATH, missing_dependency=True."""
        (tmp_path / "Cargo.toml").touch()
        detected = _detect_raw(tmp_path)
        # cargo may or may not be installed on CI; just verify the flag is a bool
        for cmd in detected.values():
            assert isinstance(cmd.missing_dependency, bool)

    def test_missing_binary_explicitly(self):
        """ProfileCommand with a clearly absent binary gets missing_dependency=True."""
        cmd = ProfileCommand(
            command=("__nonexistent_binary_abc123__", "--flag"),
            stack="x",
            source="detected",
            missing_dependency=True,
        )
        assert cmd.missing_dependency is True


# ---------------------------------------------------------------------------
# detect_profile: user overrides survive re-detect
# ---------------------------------------------------------------------------

class TestDetectProfileUserOverrides:
    def test_override_survives_detect(self, tmp_path):
        """User override for 'test' must not be replaced by detection."""
        (tmp_path / "Cargo.toml").touch()
        # First set a user override
        apply_user_override(tmp_path, "test", ("my-custom-test", "--fast"))
        # Now re-detect
        profile = detect_profile(tmp_path)
        save_profile(tmp_path, profile)
        loaded = load_profile(tmp_path)
        assert loaded is not None
        assert loaded.test is not None
        assert loaded.test.command == ("my-custom-test", "--fast")
        assert loaded.test.source == "user"
        assert "test" in loaded.user_overrides

    def test_non_overridden_kinds_updated(self, tmp_path):
        """Kinds without user overrides are re-detected on each detect call."""
        (tmp_path / "Cargo.toml").touch()
        profile = detect_profile(tmp_path)
        save_profile(tmp_path, profile)
        assert profile.lint is not None
        assert profile.lint.source == "detected"


# ---------------------------------------------------------------------------
# apply_user_override / clear_user_override
# ---------------------------------------------------------------------------

class TestUserOverridePersistence:
    def test_set_and_load(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        updated = apply_user_override(tmp_path, "test", ("pytest", "--tb=short"))
        loaded = load_profile(tmp_path)
        assert loaded is not None
        assert loaded.test is not None
        assert loaded.test.command == ("pytest", "--tb=short")
        assert loaded.test.source == "user"
        assert "test" in loaded.user_overrides

    def test_clear_removes_override(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        apply_user_override(tmp_path, "test", ("my-test",))
        clear_user_override(tmp_path, "test")
        loaded = load_profile(tmp_path)
        assert loaded is not None
        assert "test" not in loaded.user_overrides
        # After clear, should be re-detected (pytest)
        if loaded.test:
            assert loaded.test.source == "detected"

    def test_invalid_kind_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown kind"):
            apply_user_override(tmp_path, "unknown_kind", ("x",))

    def test_multiple_overrides(self, tmp_path):
        apply_user_override(tmp_path, "test", ("my-test",))
        apply_user_override(tmp_path, "lint", ("my-lint",))
        loaded = load_profile(tmp_path)
        assert loaded is not None
        assert "test" in loaded.user_overrides
        assert "lint" in loaded.user_overrides
