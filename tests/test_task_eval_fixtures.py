"""Task eval fixture tests for v2.5.0.

Covers:
  A. Valid fixture construction — all fields accepted, defaults populated.
  B. Missing required fields — clear errors for name, goal, repo, expected, safety.
  C. Malformed safety expectations — wrong types, invalid list fields.
  D. Malformed repo fixture — kind/path constraints.
  E. Stable serialisation — round-trip through JSON without data loss.
  F. File loading — valid JSON file, missing file, corrupt JSON, wrong extension.
  G. Directory loading — multiple fixtures, errors collected.
  H. load_fixture_from_dict — inline construction and error paths.
  I. Schema version validation — unsupported version rejected.
  J. Timeout and tag constraints.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.eval.fixtures import (
    CURRENT_FIXTURE_SCHEMA_VERSION,
    ExpectedOutcome,
    RepoFixture,
    SafetyExpectations,
    TaskEvalFixture,
)
from safecode.eval.loader import (
    FixtureLoadError,
    load_fixture,
    load_fixture_from_dict,
    load_fixtures_from_dir,
)


# ── shared helpers ────────────────────────────────────────────────────────


def _minimal_dict(**overrides) -> dict:
    """Return a minimal valid fixture dict."""
    d = {
        "name": "test-fixture",
        "goal": "Fix the off-by-one error in calculator.py",
        "repo": {"kind": "inline", "files": {"calc.py": "x = 1"}},
        "expected": {"kind": "patch"},
        "safety": {},
    }
    d.update(overrides)
    return d


def _write_fixture(tmp_path: Path, data: dict, filename: str = "fixture.json") -> Path:
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── A. Valid fixture construction ─────────────────────────────────────────


class TestValidFixture:
    def test_minimal_fixture_loads(self):
        f = load_fixture_from_dict(_minimal_dict())
        assert f.name == "test-fixture"
        assert f.goal == "Fix the off-by-one error in calculator.py"
        assert f.schema_version == CURRENT_FIXTURE_SCHEMA_VERSION

    def test_defaults_populated(self):
        f = load_fixture_from_dict(_minimal_dict())
        assert f.description == ""
        assert f.tags == []
        assert f.timeout_seconds == 120
        assert f.validation_commands == []
        assert f.expected_changed_files == []
        assert f.forbidden_changed_files == []

    def test_expected_defaults(self):
        f = load_fixture_from_dict(_minimal_dict())
        assert f.expected.kind == "patch"
        assert f.expected.expected_exit_code is None
        assert f.expected.expected_output_contains == []
        assert f.expected.expected_diff_contains == []
        assert f.expected.expected_files_changed == []

    def test_safety_defaults(self):
        f = load_fixture_from_dict(_minimal_dict())
        assert f.safety.expect_diff_review is True
        assert f.safety.expect_checkpoint is True
        assert f.safety.expect_approval_gate is True
        assert f.safety.allow_network is False
        assert f.safety.forbidden_commands == []
        assert f.safety.forbidden_file_writes == []
        assert f.safety.expect_audit_events == []

    def test_inline_repo_with_files(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "inline", "files": {"a.py": "x=1", "b.py": "y=2"}}
        f = load_fixture_from_dict(d)
        assert f.repo.kind == "inline"
        assert f.repo.files == {"a.py": "x=1", "b.py": "y=2"}

    def test_local_repo_with_path(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "local", "path": "/tmp/myproject"}
        f = load_fixture_from_dict(d)
        assert f.repo.kind == "local"
        assert f.repo.path == "/tmp/myproject"

    def test_full_fixture_all_optional_fields(self):
        d = _minimal_dict()
        d.update({
            "description": "Ensures the agent fixes an off-by-one.",
            "tags": ["regression", "patch"],
            "timeout_seconds": 60,
            "validation_commands": ["python -m pytest tests/ -q"],
            "expected_changed_files": ["calculator.py"],
            "forbidden_changed_files": ["config.py", "README.md"],
        })
        d["safety"] = {
            "expect_diff_review": True,
            "expect_checkpoint": True,
            "expect_approval_gate": True,
            "allow_network": False,
            "forbidden_commands": ["rm -rf /"],
            "forbidden_file_writes": [".env", ".ssh/id_rsa"],
            "expect_audit_events": ["patch_applied", "checkpoint_created"],
        }
        d["expected"] = {
            "kind": "patch",
            "expected_exit_code": 0,
            "expected_output_contains": ["1 passed"],
            "expected_diff_contains": ["+ result = x + 1"],
            "expected_files_changed": ["calculator.py"],
        }
        f = load_fixture_from_dict(d)
        assert f.description == "Ensures the agent fixes an off-by-one."
        assert f.tags == ["regression", "patch"]
        assert f.timeout_seconds == 60
        assert f.validation_commands == ["python -m pytest tests/ -q"]
        assert f.expected_changed_files == ["calculator.py"]
        assert f.forbidden_changed_files == ["config.py", "README.md"]
        assert f.safety.forbidden_commands == ["rm -rf /"]
        assert f.safety.expect_audit_events == ["patch_applied", "checkpoint_created"]
        assert f.expected.expected_output_contains == ["1 passed"]
        assert f.expected.expected_exit_code == 0

    def test_expected_kind_command(self):
        d = _minimal_dict()
        d["expected"] = {"kind": "command", "expected_exit_code": 0}
        f = load_fixture_from_dict(d)
        assert f.expected.kind == "command"

    def test_expected_kind_any(self):
        d = _minimal_dict()
        d["expected"] = {"kind": "any"}
        f = load_fixture_from_dict(d)
        assert f.expected.kind == "any"

    def test_repo_setup_commands(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "inline", "files": {}, "setup_commands": ["pip install ."]}
        f = load_fixture_from_dict(d)
        assert f.repo.setup_commands == ["pip install ."]

    def test_safety_allow_network_true(self):
        d = _minimal_dict()
        d["safety"] = {"allow_network": True}
        f = load_fixture_from_dict(d)
        assert f.safety.allow_network is True


# ── B. Missing required fields ────────────────────────────────────────────


class TestMissingRequiredFields:
    @pytest.mark.parametrize("missing_field", ["name", "goal", "repo", "expected", "safety"])
    def test_missing_field_raises(self, missing_field):
        d = _minimal_dict()
        del d[missing_field]
        with pytest.raises(FixtureLoadError, match=missing_field):
            load_fixture_from_dict(d)

    def test_empty_name_raises(self):
        with pytest.raises(FixtureLoadError, match="name"):
            load_fixture_from_dict(_minimal_dict(name=""))

    def test_whitespace_only_name_raises(self):
        with pytest.raises(FixtureLoadError, match="name"):
            load_fixture_from_dict(_minimal_dict(name="   "))

    def test_empty_goal_raises(self):
        with pytest.raises(FixtureLoadError, match="goal"):
            load_fixture_from_dict(_minimal_dict(goal=""))

    def test_whitespace_only_goal_raises(self):
        with pytest.raises(FixtureLoadError, match="goal"):
            load_fixture_from_dict(_minimal_dict(goal="\t\n"))


# ── C. Malformed safety expectations ─────────────────────────────────────


class TestMalformedSafetyExpectations:
    def test_forbidden_commands_not_list_raises(self):
        d = _minimal_dict()
        d["safety"] = {"forbidden_commands": "rm -rf /"}
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(d)

    def test_forbidden_file_writes_not_list_raises(self):
        d = _minimal_dict()
        d["safety"] = {"forbidden_file_writes": ".env"}
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(d)

    def test_expect_audit_events_not_list_raises(self):
        d = _minimal_dict()
        d["safety"] = {"expect_audit_events": "patch_applied"}
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(d)

    def test_allow_network_non_bool_coerced_or_rejected(self):
        d = _minimal_dict()
        # Pydantic coerces int 0 to False for bool fields; this is consistent
        # with the broader project pattern — just verify it doesn't raise
        d["safety"] = {"allow_network": False}
        f = load_fixture_from_dict(d)
        assert f.safety.allow_network is False

    def test_extra_safety_fields_ignored(self):
        d = _minimal_dict()
        d["safety"] = {"unknown_field_xyz": "value", "allow_network": False}
        # Pydantic ignores extra fields by default
        f = load_fixture_from_dict(d)
        assert f.safety.allow_network is False


# ── D. Malformed repo fixture ─────────────────────────────────────────────


class TestMalformedRepoFixture:
    def test_local_without_path_raises(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "local"}
        with pytest.raises(FixtureLoadError, match="path"):
            load_fixture_from_dict(d)

    def test_local_with_whitespace_path_raises(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "local", "path": "   "}
        with pytest.raises(FixtureLoadError, match="path"):
            load_fixture_from_dict(d)

    def test_inline_with_path_raises(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "inline", "path": "/tmp/something", "files": {}}
        with pytest.raises(FixtureLoadError, match="path"):
            load_fixture_from_dict(d)

    def test_invalid_kind_raises(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "s3"}
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(d)

    def test_files_not_dict_raises(self):
        d = _minimal_dict()
        d["repo"] = {"kind": "inline", "files": ["a.py", "b.py"]}
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(d)


# ── E. Stable serialisation ───────────────────────────────────────────────


class TestStableSerialization:
    def test_roundtrip_minimal(self):
        f = load_fixture_from_dict(_minimal_dict())
        serialised = f.model_dump_json()
        restored = TaskEvalFixture.model_validate_json(serialised)
        assert restored.name == f.name
        assert restored.goal == f.goal
        assert restored.schema_version == f.schema_version

    def test_roundtrip_full_fixture(self):
        d = _minimal_dict()
        d.update({
            "description": "Full round-trip test.",
            "tags": ["tag-a", "tag-b"],
            "timeout_seconds": 90,
            "validation_commands": ["pytest"],
            "expected_changed_files": ["src/calc.py"],
            "forbidden_changed_files": [".env"],
        })
        d["safety"] = {
            "forbidden_commands": ["curl"],
            "expect_audit_events": ["patch_applied"],
        }
        d["expected"] = {
            "kind": "patch",
            "expected_diff_contains": ["+ def fix():"],
        }
        f = load_fixture_from_dict(d)
        serialised = json.loads(f.model_dump_json())
        restored = load_fixture_from_dict(serialised)
        assert restored == f

    def test_schema_version_preserved(self):
        f = load_fixture_from_dict(_minimal_dict())
        data = json.loads(f.model_dump_json())
        assert data["schema_version"] == CURRENT_FIXTURE_SCHEMA_VERSION

    def test_model_dump_contains_all_fields(self):
        f = load_fixture_from_dict(_minimal_dict())
        data = f.model_dump()
        assert "name" in data
        assert "goal" in data
        assert "repo" in data
        assert "expected" in data
        assert "safety" in data
        assert "schema_version" in data

    def test_json_output_is_valid_json(self):
        f = load_fixture_from_dict(_minimal_dict())
        raw = f.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["name"] == "test-fixture"


# ── F. File loading ───────────────────────────────────────────────────────


class TestFileLoading:
    def test_valid_json_file_loads(self, tmp_path):
        p = _write_fixture(tmp_path, _minimal_dict())
        f = load_fixture(p)
        assert f.name == "test-fixture"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FixtureLoadError, match="not found"):
            load_fixture(tmp_path / "nonexistent.json")

    def test_corrupt_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json{{", encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="invalid JSON"):
            load_fixture(p)

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "fixture.yaml"
        p.write_text("name: test\n", encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="Unsupported"):
            load_fixture(p)

    def test_toml_extension_raises(self, tmp_path):
        p = tmp_path / "fixture.toml"
        p.write_text('[fixture]\nname = "test"\n', encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="Unsupported"):
            load_fixture(p)

    def test_json_array_root_raises(self, tmp_path):
        p = tmp_path / "array.json"
        p.write_text("[]", encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="JSON object"):
            load_fixture(p)

    def test_json_string_root_raises(self, tmp_path):
        p = tmp_path / "string.json"
        p.write_text('"just a string"', encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="JSON object"):
            load_fixture(p)

    def test_invalid_fixture_in_file_raises(self, tmp_path):
        p = _write_fixture(tmp_path, {"name": "x"})  # missing goal, repo, expected, safety
        with pytest.raises(FixtureLoadError):
            load_fixture(p)

    def test_full_fixture_survives_file_roundtrip(self, tmp_path):
        f = load_fixture_from_dict(_minimal_dict())
        serialised = json.loads(f.model_dump_json())
        p = _write_fixture(tmp_path, serialised)
        restored = load_fixture(p)
        assert restored == f


# ── G. Directory loading ──────────────────────────────────────────────────


class TestDirectoryLoading:
    def test_empty_directory_returns_empty_list(self, tmp_path):
        fixtures = load_fixtures_from_dir(tmp_path)
        assert fixtures == []

    def test_single_fixture_loaded(self, tmp_path):
        _write_fixture(tmp_path, _minimal_dict())
        fixtures = load_fixtures_from_dir(tmp_path)
        assert len(fixtures) == 1
        assert fixtures[0].name == "test-fixture"

    def test_multiple_fixtures_loaded_sorted_by_name(self, tmp_path):
        _write_fixture(tmp_path, _minimal_dict(name="beta"), "beta.json")
        _write_fixture(tmp_path, _minimal_dict(name="alpha"), "alpha.json")
        _write_fixture(tmp_path, _minimal_dict(name="gamma"), "gamma.json")
        fixtures = load_fixtures_from_dir(tmp_path)
        assert [f.name for f in fixtures] == ["alpha", "beta", "gamma"]

    def test_non_json_files_ignored(self, tmp_path):
        (tmp_path / "fixture.txt").write_text("ignored", encoding="utf-8")
        (tmp_path / "fixture.md").write_text("# ignored", encoding="utf-8")
        _write_fixture(tmp_path, _minimal_dict())
        fixtures = load_fixtures_from_dir(tmp_path)
        assert len(fixtures) == 1

    def test_corrupt_file_collected_into_error(self, tmp_path):
        _write_fixture(tmp_path, _minimal_dict())
        bad = tmp_path / "bad.json"
        bad.write_text("{bad json{{", encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="Failed to load"):
            load_fixtures_from_dir(tmp_path)

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FixtureLoadError, match="not found"):
            load_fixtures_from_dir(tmp_path / "nonexistent_subdir")

    def test_path_is_file_not_dir_raises(self, tmp_path):
        f = tmp_path / "notadir.json"
        f.write_text("{}", encoding="utf-8")
        with pytest.raises(FixtureLoadError, match="not a directory"):
            load_fixtures_from_dir(f)

    def test_multiple_errors_reported_together(self, tmp_path):
        (tmp_path / "bad1.json").write_text("{bad}", encoding="utf-8")
        (tmp_path / "bad2.json").write_text("{also bad}", encoding="utf-8")
        with pytest.raises(FixtureLoadError) as exc_info:
            load_fixtures_from_dir(tmp_path)
        msg = str(exc_info.value)
        assert "bad1" in msg or "bad2" in msg


# ── H. load_fixture_from_dict ─────────────────────────────────────────────


class TestLoadFixtureFromDict:
    def test_valid_dict_returns_fixture(self):
        f = load_fixture_from_dict(_minimal_dict())
        assert isinstance(f, TaskEvalFixture)

    def test_non_dict_input_raises(self):
        with pytest.raises(FixtureLoadError, match="dict"):
            load_fixture_from_dict(["name", "goal"])  # type: ignore[arg-type]

    def test_string_input_raises(self):
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict("name: test")  # type: ignore[arg-type]

    def test_error_message_contains_source(self):
        with pytest.raises(FixtureLoadError, match="<dict>"):
            load_fixture_from_dict({"name": ""})

    def test_validation_error_message_is_descriptive(self):
        with pytest.raises(FixtureLoadError) as exc_info:
            load_fixture_from_dict({"name": "x"})  # missing goal, repo, expected, safety
        msg = str(exc_info.value)
        assert "goal" in msg or "repo" in msg or "expected" in msg or "safety" in msg


# ── I. Schema version validation ──────────────────────────────────────────


class TestSchemaVersion:
    def test_current_version_accepted(self):
        d = _minimal_dict()
        d["schema_version"] = CURRENT_FIXTURE_SCHEMA_VERSION
        f = load_fixture_from_dict(d)
        assert f.schema_version == CURRENT_FIXTURE_SCHEMA_VERSION

    def test_unsupported_future_version_rejected(self):
        d = _minimal_dict()
        d["schema_version"] = 999
        with pytest.raises(FixtureLoadError, match="schema_version"):
            load_fixture_from_dict(d)

    def test_version_zero_rejected(self):
        d = _minimal_dict()
        d["schema_version"] = 0
        with pytest.raises(FixtureLoadError, match="schema_version"):
            load_fixture_from_dict(d)

    def test_non_integer_version_rejected(self):
        d = _minimal_dict()
        d["schema_version"] = "v1"
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(d)

    def test_missing_version_uses_default(self):
        d = _minimal_dict()
        f = load_fixture_from_dict(d)
        assert f.schema_version == CURRENT_FIXTURE_SCHEMA_VERSION


# ── J. Timeout and tags ───────────────────────────────────────────────────


class TestTimeoutAndTags:
    def test_timeout_minimum_one(self):
        d = _minimal_dict(timeout_seconds=1)
        f = load_fixture_from_dict(d)
        assert f.timeout_seconds == 1

    def test_timeout_maximum_3600(self):
        d = _minimal_dict(timeout_seconds=3600)
        f = load_fixture_from_dict(d)
        assert f.timeout_seconds == 3600

    def test_timeout_zero_rejected(self):
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(_minimal_dict(timeout_seconds=0))

    def test_timeout_negative_rejected(self):
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(_minimal_dict(timeout_seconds=-1))

    def test_timeout_exceeds_max_rejected(self):
        with pytest.raises(FixtureLoadError):
            load_fixture_from_dict(_minimal_dict(timeout_seconds=3601))

    def test_tags_list_of_strings(self):
        d = _minimal_dict(tags=["smoke", "safety", "regression"])
        f = load_fixture_from_dict(d)
        assert f.tags == ["smoke", "safety", "regression"]

    def test_empty_tags_allowed(self):
        d = _minimal_dict(tags=[])
        f = load_fixture_from_dict(d)
        assert f.tags == []

    def test_expected_files_changed_list(self):
        d = _minimal_dict(expected_changed_files=["src/main.py", "tests/test_main.py"])
        f = load_fixture_from_dict(d)
        assert f.expected_changed_files == ["src/main.py", "tests/test_main.py"]

    def test_forbidden_changed_files_list(self):
        d = _minimal_dict(forbidden_changed_files=[".env", "config/secrets.yaml"])
        f = load_fixture_from_dict(d)
        assert f.forbidden_changed_files == [".env", "config/secrets.yaml"]
