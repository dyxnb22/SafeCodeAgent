"""Tests for the v2.2.1 model tool call adapter."""

from __future__ import annotations

import pytest

from safecode.tools.adapter import AdapterError, ToolCallAdapter, ToolCallValidationResult
from safecode.tools.registry import PermissionCategory, ToolRegistry, ToolRiskLevel


# ── ToolCallAdapter.validate() ────────────────────────────────────────────────


class TestAdapterValidate:
    def test_valid_known_tool_returns_result(self):
        result = ToolCallAdapter().validate("context.read", {"target": "README.md"})
        assert isinstance(result, ToolCallValidationResult)
        assert result.tool_name == "context.read"
        assert result.resolved_args == {"target": "README.md"}

    def test_valid_result_carries_spec(self):
        result = ToolCallAdapter().validate("context.read", {"target": "src/main.py"})
        assert result.spec.name == "context.read"
        assert result.spec.permission_category == PermissionCategory.READ

    def test_valid_result_carries_approval_metadata(self):
        result = ToolCallAdapter().validate("context.read", {"target": "README.md"})
        assert result.requires_approval is False
        assert result.risk == ToolRiskLevel.LOW
        assert result.permission_category == PermissionCategory.READ

    def test_valid_result_carries_audit_event(self):
        result = ToolCallAdapter().validate("context.read", {"target": "README.md"})
        assert result.audit_event is not None
        assert result.audit_event.event_type == "file_read"

    def test_optional_arg_can_be_omitted(self):
        result = ToolCallAdapter().validate("context.collect", {"query": "check tests"})
        assert result.resolved_args["query"] == "check tests"
        assert "limit" not in result.resolved_args

    def test_all_args_included_are_preserved(self):
        result = ToolCallAdapter().validate(
            "context.collect", {"query": "task", "limit": 5}
        )
        assert result.resolved_args["limit"] == 5

    def test_result_is_frozen(self):
        result = ToolCallAdapter().validate("context.read", {"target": "x.py"})
        with pytest.raises(Exception):
            result.tool_name = "other"  # type: ignore[misc]


# ── Unknown tool rejection ─────────────────────────────────────────────────────


class TestAdapterUnknownTool:
    def test_unknown_tool_raises_adapter_error(self):
        with pytest.raises(AdapterError, match="Unknown tool"):
            ToolCallAdapter().validate("nonexistent.tool", {})

    def test_empty_tool_name_raises_adapter_error(self):
        with pytest.raises(AdapterError, match="Unknown tool"):
            ToolCallAdapter().validate("", {})

    def test_similar_but_wrong_name_raises_adapter_error(self):
        with pytest.raises(AdapterError, match="Unknown tool"):
            ToolCallAdapter().validate("context.write", {})

    def test_unknown_tool_does_not_mutate_registry(self):
        adapter = ToolCallAdapter()
        names_before = adapter._registry.names()
        try:
            adapter.validate("fake.tool", {})
        except AdapterError:
            pass
        names_after = adapter._registry.names()
        assert names_before == names_after


# ── Missing required args ─────────────────────────────────────────────────────


class TestAdapterMissingRequiredArgs:
    def test_missing_required_arg_raises_adapter_error(self):
        with pytest.raises(AdapterError, match="Missing required argument"):
            ToolCallAdapter().validate("context.read", {})

    def test_missing_target_for_patch_propose(self):
        with pytest.raises(AdapterError, match="Missing required argument.*target"):
            ToolCallAdapter().validate("patch.propose", {"patch_text": "--- a\n+++ b\n"})

    def test_missing_patch_text_for_patch_propose(self):
        with pytest.raises(AdapterError, match="Missing required argument.*patch_text"):
            ToolCallAdapter().validate("patch.propose", {"target": "src/app.py"})

    def test_missing_command_for_shell_propose(self):
        with pytest.raises(AdapterError, match="Missing required argument.*command"):
            ToolCallAdapter().validate("shell.propose", {})

    def test_missing_proposal_id_for_sandbox_execute(self):
        with pytest.raises(AdapterError, match="Missing required argument.*proposal_id"):
            ToolCallAdapter().validate("sandbox.execute", {})


# ── Invalid arg types ─────────────────────────────────────────────────────────


class TestAdapterInvalidArgTypes:
    def test_path_arg_must_be_str(self):
        with pytest.raises(AdapterError, match="expected path"):
            ToolCallAdapter().validate("context.read", {"target": 123})

    def test_str_arg_must_be_str(self):
        with pytest.raises(AdapterError, match="expected str"):
            ToolCallAdapter().validate("context.collect", {"query": ["not", "a", "str"]})

    def test_int_arg_must_be_int(self):
        with pytest.raises(AdapterError, match="expected int"):
            ToolCallAdapter().validate("context.collect", {"query": "task", "limit": "ten"})

    def test_bool_arg_must_be_bool(self):
        with pytest.raises(AdapterError, match="expected bool"):
            ToolCallAdapter().validate(
                "shell.run", {"command": "pytest", "approved": "yes"}
            )

    def test_dict_arg_must_be_dict(self):
        with pytest.raises(AdapterError, match="expected dict"):
            ToolCallAdapter().validate(
                "mcp.call_readonly",
                {"tool_name": "notion.search", "input_json": "not-a-dict"},
            )

    def test_correct_types_pass(self):
        result = ToolCallAdapter().validate(
            "mcp.call_readonly",
            {"tool_name": "notion.search", "input_json": {"q": "hello"}},
        )
        assert result.requires_approval is False


# ── Approval metadata for write/shell/high-risk tools ─────────────────────────


class TestAdapterApprovalMetadata:
    def test_write_tool_requires_approval(self):
        result = ToolCallAdapter().validate(
            "patch.propose", {"target": "src/app.py", "patch_text": "--- a\n+++ b\n"}
        )
        assert result.requires_approval is True
        assert result.permission_category == PermissionCategory.WRITE

    def test_shell_tool_requires_approval(self):
        result = ToolCallAdapter().validate("shell.propose", {"command": "pytest -q"})
        assert result.requires_approval is True
        assert result.permission_category == PermissionCategory.SHELL

    def test_high_risk_sandbox_execute_requires_approval(self):
        result = ToolCallAdapter().validate(
            "sandbox.execute", {"proposal_id": "abc123"}
        )
        assert result.requires_approval is True
        assert result.risk == ToolRiskLevel.HIGH

    def test_read_tool_does_not_require_approval(self):
        result = ToolCallAdapter().validate("context.read", {"target": "README.md"})
        assert result.requires_approval is False
        assert result.risk == ToolRiskLevel.LOW

    def test_audit_verify_does_not_require_approval(self):
        result = ToolCallAdapter().validate("audit.verify", {})
        assert result.requires_approval is False
        assert result.permission_category == PermissionCategory.AUDIT

    def test_all_write_tools_require_approval(self):
        registry = ToolRegistry()
        adapter = ToolCallAdapter(registry)
        for spec in registry.by_permission(PermissionCategory.WRITE):
            assert spec.requires_human_approval, f"{spec.name} is WRITE but no approval"

    def test_all_shell_tools_require_approval(self):
        registry = ToolRegistry()
        for spec in registry.by_permission(PermissionCategory.SHELL):
            assert spec.requires_human_approval, f"{spec.name} is SHELL but no approval"

    def test_all_high_risk_tools_require_approval(self):
        registry = ToolRegistry()
        for spec in registry.by_risk(ToolRiskLevel.HIGH):
            assert spec.requires_human_approval, f"{spec.name} is HIGH but no approval"


# ── ToolCallAdapter.lookup() ─────────────────────────────────────────────────


class TestAdapterLookup:
    def test_lookup_known_tool_returns_spec(self):
        spec = ToolCallAdapter().lookup("patch.propose")
        assert spec.name == "patch.propose"

    def test_lookup_unknown_raises_adapter_error(self):
        with pytest.raises(AdapterError, match="Unknown tool"):
            ToolCallAdapter().lookup("bad.tool")


# ── Router still handles valid intents (backward compat) ──────────────────────


class TestRouterWithRegistryBackedValidation:
    def test_read_intent_still_routes_without_approval(self):
        from safecode.agent.tools import ToolIntentRouter

        routed = ToolIntentRouter().route(
            {"type": "read", "target": "README.md", "description": "inspect"}
        )
        assert routed.route == "context.read"
        assert routed.executable_now is True
        assert routed.intent.requires_approval is False

    def test_patch_intent_still_requires_approval(self):
        from safecode.agent.tools import ToolIntentRouter

        routed = ToolIntentRouter().route({"type": "patch", "target": "src/app.py"})
        assert routed.route == "patch.propose"
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True

    def test_shell_intent_still_requires_approval(self):
        from safecode.agent.tools import ToolIntentRouter

        routed = ToolIntentRouter().route({"type": "shell", "command": "pytest -q"})
        assert routed.route == "shell.propose"
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True

    def test_sandbox_intent_still_requires_approval(self):
        from safecode.agent.tools import ToolIntentRouter

        routed = ToolIntentRouter().route({"type": "sandbox", "command": "pytest -q"})
        assert routed.route == "sandbox.propose"
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True

    def test_mcp_intent_still_requires_approval(self):
        from safecode.agent.tools import ToolIntentRouter

        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.search"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True

    def test_report_intent_still_routes_without_approval(self):
        from safecode.agent.tools import ToolIntentRouter

        routed = ToolIntentRouter().route(
            {"type": "report", "target": "session-abc", "description": "render"}
        )
        assert routed.route == "report.render"
        assert routed.executable_now is True

    def test_unknown_intent_still_fails_closed(self):
        from safecode.agent.tools import ToolIntentRouter

        with pytest.raises(ValueError, match="Invalid tool intent"):
            ToolIntentRouter().route({"type": "unknown", "target": "x"})


# ── No execution or write side effects ───────────────────────────────────────


class TestAdapterNoSideEffects:
    def test_adapter_does_not_execute_any_tool(self, monkeypatch):
        import subprocess

        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        ToolCallAdapter().validate("context.read", {"target": "README.md"})
        assert not called

    def test_adapter_does_not_write_files(self, tmp_path):
        import os

        before = set(os.listdir(tmp_path))
        try:
            ToolCallAdapter().validate("patch.propose", {"target": "x.py", "patch_text": "diff"})
        except Exception:
            pass
        after = set(os.listdir(tmp_path))
        assert before == after

    def test_adapter_does_not_call_llm(self, monkeypatch):
        called = []

        def fake_create(*args, **kwargs):
            called.append(1)

        monkeypatch.setattr(
            "safecode.llm.factory.create_llm_client", fake_create, raising=False
        )
        ToolCallAdapter().validate("context.read", {"target": "README.md"})
        assert not called
