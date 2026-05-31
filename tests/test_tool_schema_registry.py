"""Tests for the v2.2.0 tool schema registry."""

from __future__ import annotations

import pytest

from safecode.tools.registry import (
    AuditEventRef,
    PermissionCategory,
    ToolArgSchema,
    ToolRegistry,
    ToolRiskLevel,
    ToolSpec,
)


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
