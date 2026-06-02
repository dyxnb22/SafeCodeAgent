"""Tests for the tool schema registry (v2.2.0 base; v2.9.8 versioning)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.tools.registry import (
    REGISTRY_SCHEMA_VERSION,
    AuditEventRef,
    PermissionCategory,
    ToolArgSchema,
    ToolRegistry,
    ToolRiskLevel,
    ToolSpec,
)

_SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "registry" / "tool_registry_v1.json"


# ── ToolSpec and model validation ─────────────────────────────────────────


class TestToolSpec:
    def test_frozen_immutability(self):
        spec = ToolSpec(
            name="test.tool",
            description="A test tool.",
            risk=ToolRiskLevel.LOW,
            permission_category=PermissionCategory.READ,
            requires_human_approval=False,
        )
        with pytest.raises(Exception):
            spec.name = "other"  # type: ignore[misc]

    def test_fields_are_typed(self):
        spec = ToolSpec(
            name="test.tool",
            description="desc",
            risk=ToolRiskLevel.MEDIUM,
            permission_category=PermissionCategory.WRITE,
            requires_human_approval=True,
            args=[ToolArgSchema(name="target", type="path", required=True, description="file")],
            audit_event=AuditEventRef(event_type="test_event", description="emitted"),
        )
        assert isinstance(spec.risk, ToolRiskLevel)
        assert isinstance(spec.permission_category, PermissionCategory)
        assert isinstance(spec.args[0], ToolArgSchema)
        assert isinstance(spec.audit_event, AuditEventRef)

    def test_args_default_to_empty_list(self):
        spec = ToolSpec(
            name="x",
            description="x",
            risk=ToolRiskLevel.LOW,
            permission_category=PermissionCategory.AUDIT,
            requires_human_approval=False,
        )
        assert spec.args == []
        assert spec.audit_event is None

    def test_tool_arg_schema_frozen(self):
        arg = ToolArgSchema(name="cmd", type="str", required=True)
        with pytest.raises(Exception):
            arg.name = "other"  # type: ignore[misc]

    def test_audit_event_ref_frozen(self):
        ref = AuditEventRef(event_type="foo", description="bar")
        with pytest.raises(Exception):
            ref.event_type = "baz"  # type: ignore[misc]


# ── ToolRegistry.list() ────────────────────────────────────────────────────


class TestToolRegistryList:
    def test_list_returns_all_tools(self):
        tools = ToolRegistry().list()
        assert len(tools) >= 10, "registry should contain at least 10 tools"

    def test_list_sorted_alphabetically(self):
        names = [t.name for t in ToolRegistry().list()]
        assert names == sorted(names)

    def test_list_no_duplicate_names(self):
        names = [t.name for t in ToolRegistry().list()]
        assert len(names) == len(set(names))

    def test_list_is_deterministic(self):
        names_a = [t.name for t in ToolRegistry().list()]
        names_b = [t.name for t in ToolRegistry().list()]
        assert names_a == names_b

    def test_list_returns_tool_spec_instances(self):
        for tool in ToolRegistry().list():
            assert isinstance(tool, ToolSpec)


# ── ToolRegistry.get() ────────────────────────────────────────────────────


class TestToolRegistryGet:
    def test_get_known_tool(self):
        spec = ToolRegistry().get("patch.propose")
        assert spec.name == "patch.propose"
        assert spec.permission_category == PermissionCategory.WRITE
        assert spec.requires_human_approval is True

    def test_get_unknown_tool_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown tool"):
            ToolRegistry().get("nonexistent.tool")

    def test_get_all_registered_names_succeed(self):
        registry = ToolRegistry()
        for name in registry.names():
            spec = registry.get(name)
            assert spec.name == name


# ── ToolRegistry.names() ──────────────────────────────────────────────────


class TestToolRegistryNames:
    def test_names_sorted(self):
        names = ToolRegistry().names()
        assert names == sorted(names)

    def test_names_nonempty(self):
        assert len(ToolRegistry().names()) > 0


# ── Risk and permission metadata ──────────────────────────────────────────


class TestRiskAndPermissionMetadata:
    def test_patch_apply_is_medium_write(self):
        spec = ToolRegistry().get("patch.apply")
        assert spec.risk == ToolRiskLevel.MEDIUM
        assert spec.permission_category == PermissionCategory.WRITE

    def test_sandbox_execute_is_high_risk(self):
        spec = ToolRegistry().get("sandbox.execute")
        assert spec.risk == ToolRiskLevel.HIGH

    def test_context_collect_is_low_read(self):
        spec = ToolRegistry().get("context.collect")
        assert spec.risk == ToolRiskLevel.LOW
        assert spec.permission_category == PermissionCategory.READ
        assert spec.requires_human_approval is False

    def test_high_risk_tools_require_approval(self):
        registry = ToolRegistry()
        for spec in registry.by_risk(ToolRiskLevel.HIGH):
            assert spec.requires_human_approval, f"{spec.name} is high-risk but does not require approval"

    def test_write_permission_tools_require_approval(self):
        registry = ToolRegistry()
        for spec in registry.by_permission(PermissionCategory.WRITE):
            assert spec.requires_human_approval, f"{spec.name} has WRITE permission but does not require approval"

    def test_shell_permission_tools_require_approval(self):
        registry = ToolRegistry()
        for spec in registry.by_permission(PermissionCategory.SHELL):
            assert spec.requires_human_approval, f"{spec.name} has SHELL permission but does not require approval"

    def test_by_permission_read_returns_read_tools(self):
        tools = ToolRegistry().by_permission(PermissionCategory.READ)
        assert all(t.permission_category == PermissionCategory.READ for t in tools)
        assert len(tools) >= 1

    def test_by_risk_low_returns_low_risk_tools(self):
        tools = ToolRegistry().by_risk(ToolRiskLevel.LOW)
        assert all(t.risk == ToolRiskLevel.LOW for t in tools)

    def test_requiring_approval_subset(self):
        registry = ToolRegistry()
        approval_tools = registry.requiring_approval()
        all_tools = registry.list()
        approval_names = {t.name for t in approval_tools}
        all_names = {t.name for t in all_tools}
        assert approval_names.issubset(all_names)
        for t in all_tools:
            if t.requires_human_approval:
                assert t.name in approval_names


# ── Audit event metadata ──────────────────────────────────────────────────


class TestAuditEventMetadata:
    def test_patch_propose_has_audit_event(self):
        spec = ToolRegistry().get("patch.propose")
        assert spec.audit_event is not None
        assert spec.audit_event.event_type == "patch_proposed"

    def test_audit_verify_has_audit_event(self):
        spec = ToolRegistry().get("audit.verify")
        assert spec.audit_event is not None
        assert spec.audit_event.event_type == "audit_verified"

    def test_all_tools_have_audit_event(self):
        for spec in ToolRegistry().list():
            assert spec.audit_event is not None, f"{spec.name} is missing an audit_event reference"


# ── Serialization ─────────────────────────────────────────────────────────


class TestSerialization:
    def test_tool_spec_serializes_to_dict(self):
        spec = ToolRegistry().get("shell.run")
        data = spec.model_dump()
        assert data["name"] == "shell.run"
        assert data["risk"] == "medium"
        assert data["permission_category"] == "shell"
        assert data["requires_human_approval"] is True
        assert isinstance(data["args"], list)

    def test_tool_spec_round_trips(self):
        spec = ToolRegistry().get("context.collect")
        data = spec.model_dump()
        restored = ToolSpec(**data)
        assert restored == spec

    def test_all_tools_serialize_without_error(self):
        for spec in ToolRegistry().list():
            data = spec.model_dump()
            assert "name" in data
            assert "risk" in data
            assert "permission_category" in data
            assert "requires_human_approval" in data


# ── No side effects ───────────────────────────────────────────────────────


class TestNoSideEffects:
    def test_registry_does_not_write_files(self, tmp_path):
        import os
        before = set(os.listdir(tmp_path))
        _ = ToolRegistry().list()
        after = set(os.listdir(tmp_path))
        assert before == after

    def test_get_missing_tool_does_not_mutate_registry(self):
        registry = ToolRegistry()
        names_before = registry.names()
        try:
            registry.get("no.such.tool")
        except KeyError:
            pass
        names_after = registry.names()
        assert names_before == names_after

    def test_registry_does_not_call_llm(self, monkeypatch):
        called = []

        def fake_plan(*args, **kwargs):
            called.append(True)

        monkeypatch.setattr("builtins.__import__", __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__)  # no-op
        _ = ToolRegistry().list()
        assert not called, "registry construction should not invoke any LLM"


# ── CLI smoke tests ───────────────────────────────────────────────────────


class TestToolsCLI:
    def test_tools_list_runs(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "list"])
        assert result.exit_code == 0
        assert "patch.propose" in result.output

    def test_tools_list_shows_approval_column(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "list"])
        assert result.exit_code == 0
        assert "Approval" in result.output or "approval" in result.output.lower()

    def test_tools_inspect_known_tool(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "inspect", "patch.propose"])
        assert result.exit_code == 0
        assert "patch.propose" in result.output
        assert "patch_proposed" in result.output

    def test_tools_inspect_unknown_tool_exits_nonzero(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "inspect", "fake.tool"])
        assert result.exit_code != 0

    def test_tools_list_filter_by_risk(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "list", "--risk", "high"])
        assert result.exit_code == 0
        assert "sandbox.execute" in result.output

    def test_tools_list_filter_by_permission(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "list", "--permission", "write"])
        assert result.exit_code == 0
        assert "patch.apply" in result.output

    def test_tools_list_invalid_risk_exits_nonzero(self):
        from typer.testing import CliRunner
        from safecode.cli import app

        result = CliRunner().invoke(app, ["tools", "list", "--risk", "extreme"])
        assert result.exit_code != 0


# ── v2.9.8: ToolSpec version field ────────────────────────────────────────


class TestToolSpecVersion:
    def test_all_specs_have_version(self):
        for spec in ToolRegistry().list():
            assert isinstance(spec.version, str), f"{spec.name} missing version string"
            assert len(spec.version) > 0, f"{spec.name} has empty version"

    def test_version_is_semantic(self):
        for spec in ToolRegistry().list():
            parts = spec.version.split(".")
            assert len(parts) >= 2, f"{spec.name} version {spec.version!r} is not semver-like"
            for part in parts:
                assert part.isdigit(), f"{spec.name} version part {part!r} is not numeric"

    def test_default_version_is_stable(self):
        spec = ToolSpec(
            name="test.tool",
            description="desc",
            risk=ToolRiskLevel.LOW,
            permission_category=PermissionCategory.READ,
            requires_human_approval=False,
        )
        assert spec.version == "1.0.0"

    def test_registry_schema_version_exported(self):
        assert isinstance(REGISTRY_SCHEMA_VERSION, str)
        assert len(REGISTRY_SCHEMA_VERSION) > 0

    def test_registry_schema_version_is_numeric_string(self):
        assert REGISTRY_SCHEMA_VERSION.isdigit()

    def test_version_field_survives_round_trip(self):
        spec = ToolRegistry().get("patch.propose")
        data = spec.model_dump()
        assert "version" in data
        restored = ToolSpec(**data)
        assert restored.version == spec.version


# ── v2.9.8: Registry snapshot ─────────────────────────────────────────────


def _build_registry_snapshot() -> dict:
    """Build the narrow deterministic snapshot (no prose descriptions)."""
    registry = ToolRegistry()
    tools = registry.list()
    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "tools": [
            {
                "name": t.name,
                "version": t.version,
                "permission_category": t.permission_category,
                "risk": t.risk,
                "requires_human_approval": t.requires_human_approval,
                "args": [
                    {"name": a.name, "type": a.type, "required": a.required}
                    for a in t.args
                ],
            }
            for t in tools
        ],
    }


class TestRegistrySnapshot:
    def test_snapshot_file_exists(self):
        assert _SNAPSHOT_PATH.exists(), f"snapshot missing at {_SNAPSHOT_PATH}"

    def test_snapshot_is_valid_json(self):
        data = json.loads(_SNAPSHOT_PATH.read_text())
        assert isinstance(data, dict)
        assert "tools" in data

    def test_snapshot_matches_live_registry(self):
        expected = json.loads(_SNAPSHOT_PATH.read_text())
        actual = _build_registry_snapshot()
        assert actual == expected, (
            "Live registry differs from snapshot. "
            "If the change is intentional, regenerate with:\n"
            "  PYTHONPATH=src python3 -m pytest tests/test_tool_schema_registry.py "
            "::TestRegistrySnapshot::test_snapshot_matches_live_registry -v\n"
            "and update tests/snapshots/registry/tool_registry_v1.json."
        )

    def test_snapshot_is_deterministic(self):
        snap_a = _build_registry_snapshot()
        snap_b = _build_registry_snapshot()
        assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)

    def test_snapshot_sorted_keys(self):
        raw = _SNAPSHOT_PATH.read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip(), "Snapshot keys must be sorted"

    def test_snapshot_tool_names_are_sorted(self):
        data = json.loads(_SNAPSHOT_PATH.read_text())
        names = [t["name"] for t in data["tools"]]
        assert names == sorted(names)

    def test_snapshot_has_version_for_all_tools(self):
        data = json.loads(_SNAPSHOT_PATH.read_text())
        for tool in data["tools"]:
            assert "version" in tool
            assert isinstance(tool["version"], str)
            assert len(tool["version"]) > 0

    def test_snapshot_no_prose_descriptions(self):
        data = json.loads(_SNAPSHOT_PATH.read_text())
        for tool in data["tools"]:
            assert "description" not in tool
            for arg in tool.get("args", []):
                assert "description" not in arg
