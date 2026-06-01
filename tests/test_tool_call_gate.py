"""Tests for the v2.3.7 universal ToolCallGate."""

from __future__ import annotations

import pytest

from safecode.tools.gate import GateError, GateResult, ToolCallGate
from safecode.tools.adapter import ToolCallValidationResult
from safecode.tools.registry import PermissionCategory, ToolRiskLevel


# ── GateResult dataclass ──────────────────────────────────────────────────────


class TestGateResult:
    def test_allowed_result_is_frozen(self):
        result = GateResult(allowed=True, reason="ok")
        with pytest.raises((AttributeError, TypeError)):
            result.allowed = False  # type: ignore[misc]

    def test_blocked_result_without_validation(self):
        result = GateResult(allowed=False, reason="Unknown tool: 'bad'")
        assert result.allowed is False
        assert result.validation is None

    def test_allowed_result_with_validation(self):
        gate = ToolCallGate()
        result = gate.check("context.read", {"target": "README.md"}, approved=False)
        assert result.allowed is True
        assert result.validation is not None


# ── Gate.check() — unknown tools ─────────────────────────────────────────────


class TestGateCheckUnknownTool:
    def test_unknown_tool_is_blocked(self):
        result = ToolCallGate().check("nonexistent.tool", {})
        assert result.allowed is False
        assert "Unknown tool" in result.reason

    def test_empty_tool_name_is_blocked(self):
        result = ToolCallGate().check("", {})
        assert result.allowed is False

    def test_similar_but_wrong_name_is_blocked(self):
        result = ToolCallGate().check("context.write", {})
        assert result.allowed is False

    def test_blocked_unknown_has_no_validation(self):
        result = ToolCallGate().check("bad.tool", {})
        assert result.validation is None


# ── Gate.check() — arg validation ────────────────────────────────────────────


class TestGateCheckArgValidation:
    def test_missing_required_arg_is_blocked(self):
        result = ToolCallGate().check("context.read", {})
        assert result.allowed is False
        assert "Missing required argument" in result.reason

    def test_wrong_arg_type_is_blocked(self):
        result = ToolCallGate().check("context.read", {"target": 42})
        assert result.allowed is False
        assert "expected" in result.reason.lower()

    def test_valid_args_pass(self):
        result = ToolCallGate().check("context.read", {"target": "README.md"}, approved=False)
        assert result.allowed is True

    def test_missing_required_patch_args_blocked(self):
        result = ToolCallGate().check("patch.propose", {"target": "src/app.py"}, approved=True)
        assert result.allowed is False
        assert "patch_text" in result.reason


# ── Gate.check() — approval gating ───────────────────────────────────────────


class TestGateCheckApproval:
    def test_write_tool_without_approval_is_blocked(self):
        result = ToolCallGate().check(
            "patch.propose",
            {"target": "src/app.py", "patch_text": "--- a\n+++ b\n"},
            approved=False,
        )
        assert result.allowed is False
        assert "requires human approval" in result.reason

    def test_write_tool_with_approval_is_allowed(self):
        result = ToolCallGate().check(
            "patch.propose",
            {"target": "src/app.py", "patch_text": "--- a\n+++ b\n"},
            approved=True,
        )
        assert result.allowed is True

    def test_shell_tool_without_approval_is_blocked(self):
        result = ToolCallGate().check("shell.propose", {"command": "pytest -q"}, approved=False)
        assert result.allowed is False

    def test_shell_tool_with_approval_is_allowed(self):
        result = ToolCallGate().check("shell.propose", {"command": "pytest -q"}, approved=True)
        assert result.allowed is True

    def test_sandbox_execute_without_approval_is_blocked(self):
        result = ToolCallGate().check("sandbox.execute", {"proposal_id": "abc123"}, approved=False)
        assert result.allowed is False
        assert result.validation is not None
        assert result.validation.risk == ToolRiskLevel.HIGH

    def test_sandbox_execute_with_approval_is_allowed(self):
        result = ToolCallGate().check("sandbox.execute", {"proposal_id": "abc123"}, approved=True)
        assert result.allowed is True

    def test_read_tool_allowed_without_approval(self):
        result = ToolCallGate().check("context.read", {"target": "README.md"}, approved=False)
        assert result.allowed is True

    def test_audit_verify_allowed_without_approval(self):
        result = ToolCallGate().check("audit.verify", {}, approved=False)
        assert result.allowed is True

    def test_blocked_write_exposes_validation_metadata(self):
        result = ToolCallGate().check(
            "patch.apply", {"patch_id": "abc"}, approved=False
        )
        assert result.allowed is False
        assert result.validation is not None
        assert result.validation.permission_category == PermissionCategory.WRITE
        assert result.validation.requires_approval is True

    def test_all_write_tools_blocked_without_approval(self):
        from safecode.tools.registry import PermissionCategory, ToolRegistry

        registry = ToolRegistry()
        gate = ToolCallGate(registry)
        for spec in registry.by_permission(PermissionCategory.WRITE):
            r = gate.check_intent(spec.name, approved=False)
            assert r.allowed is False, f"{spec.name} should require approval"

    def test_all_shell_tools_blocked_without_approval(self):
        from safecode.tools.registry import PermissionCategory, ToolRegistry

        registry = ToolRegistry()
        gate = ToolCallGate(registry)
        for spec in registry.by_permission(PermissionCategory.SHELL):
            r = gate.check_intent(spec.name, approved=False)
            assert r.allowed is False, f"{spec.name} should require approval"


# ── Gate.check_intent() ───────────────────────────────────────────────────────


class TestGateCheckIntent:
    def test_known_read_tool_allowed_without_approval(self):
        result = ToolCallGate().check_intent("context.read", approved=False)
        assert result.allowed is True

    def test_known_write_tool_blocked_without_approval(self):
        result = ToolCallGate().check_intent("patch.apply", approved=False)
        assert result.allowed is False
        assert "requires human approval" in result.reason

    def test_known_write_tool_allowed_with_approval(self):
        result = ToolCallGate().check_intent("patch.apply", approved=True)
        assert result.allowed is True

    def test_unknown_tool_is_blocked(self):
        result = ToolCallGate().check_intent("fake.tool", approved=True)
        assert result.allowed is False

    def test_result_carries_risk_and_permission(self):
        result = ToolCallGate().check_intent("patch.apply", approved=True)
        assert result.validation is not None
        assert result.validation.risk == ToolRiskLevel.MEDIUM
        assert result.validation.permission_category == PermissionCategory.WRITE

    def test_intent_check_skips_arg_validation(self):
        # patch.apply requires patch_id arg, but check_intent doesn't validate args.
        result = ToolCallGate().check_intent("patch.apply", approved=True)
        assert result.allowed is True


# ── Gate.must_pass() / must_pass_intent() ─────────────────────────────────────


class TestGateMustPass:
    def test_allowed_call_returns_validation(self):
        validation = ToolCallGate().must_pass(
            "context.read", {"target": "README.md"}, approved=False
        )
        assert isinstance(validation, ToolCallValidationResult)
        assert validation.tool_name == "context.read"

    def test_blocked_call_raises_gate_error(self):
        with pytest.raises(GateError, match="Unknown tool"):
            ToolCallGate().must_pass("fake.tool", {})

    def test_unapproved_write_raises_gate_error(self):
        with pytest.raises(GateError, match="requires human approval"):
            ToolCallGate().must_pass(
                "patch.propose",
                {"target": "src/app.py", "patch_text": "diff"},
                approved=False,
            )

    def test_gate_error_is_value_error_subclass(self):
        with pytest.raises(ValueError):
            ToolCallGate().must_pass("bad.tool", {})

    def test_must_pass_intent_allowed(self):
        validation = ToolCallGate().must_pass_intent("context.read", approved=False)
        assert validation.tool_name == "context.read"

    def test_must_pass_intent_blocked_raises(self):
        with pytest.raises(GateError):
            ToolCallGate().must_pass_intent("patch.apply", approved=False)


# ── No side effects ───────────────────────────────────────────────────────────


class TestGateNoSideEffects:
    def test_gate_does_not_execute_subprocess(self, monkeypatch):
        import subprocess

        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        ToolCallGate().check("patch.apply", {"patch_id": "abc"}, approved=True)
        assert not called

    def test_gate_does_not_write_files(self, tmp_path):
        import os

        before = set(os.listdir(tmp_path))
        try:
            ToolCallGate().check("sandbox.execute", {"proposal_id": "x"}, approved=True)
        except Exception:
            pass
        after = set(os.listdir(tmp_path))
        assert before == after

    def test_gate_does_not_call_llm(self, monkeypatch):
        called = []

        monkeypatch.setattr(
            "safecode.llm.factory.create_llm_client",
            lambda *a, **kw: called.append(1),
            raising=False,
        )
        ToolCallGate().check("context.read", {"target": "x.py"}, approved=False)
        assert not called


# ── CLI paths import the gate ─────────────────────────────────────────────────


class TestCLIGateImports:
    def test_cli_core_imports_gate(self):
        import safecode.cli_core as m

        assert hasattr(m, "ToolCallGate")

    def test_cli_sandbox_imports_gate(self):
        import safecode.cli_sandbox as m

        assert hasattr(m, "ToolCallGate")

    def test_cli_mcp_imports_gate(self):
        import safecode.cli_mcp as m

        assert hasattr(m, "ToolCallGate")

    def test_gate_is_consulted_on_edit(self, tmp_path, monkeypatch):
        """sac edit path goes through the gate (gate is imported and used)."""
        from safecode.tools.gate import ToolCallGate as _Gate

        consulted = []
        original_check_intent = _Gate.check_intent

        def spy_check_intent(self, tool_name, *, approved=False):
            consulted.append(tool_name)
            return original_check_intent(self, tool_name, approved=approved)

        monkeypatch.setattr(_Gate, "check_intent", spy_check_intent)
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        runner.invoke(app, ["edit", "fix something"])
        assert "patch.propose" in consulted

    def test_gate_is_consulted_on_sandbox_execute(self, tmp_path, monkeypatch):
        from safecode.tools.gate import ToolCallGate as _Gate

        consulted = []
        original_check_intent = _Gate.check_intent

        def spy_check_intent(self, tool_name, *, approved=False):
            consulted.append(tool_name)
            return original_check_intent(self, tool_name, approved=approved)

        monkeypatch.setattr(_Gate, "check_intent", spy_check_intent)
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        runner.invoke(app, ["sandbox", "execute"])
        assert "sandbox.execute" in consulted
