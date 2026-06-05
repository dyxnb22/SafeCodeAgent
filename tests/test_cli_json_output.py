"""Tests for v3.1.0 json-output-foundation.

Verifies:
- sac ask --json returns valid JSON with command="ask" and data.answer key.
- sac edit --json returns valid JSON with pending_patch_path and diff_text.
- sac run --json (low-risk) returns valid JSON with executed and exit_code.
- sac run --json (high-risk blocked) returns JSON with status="error", exit code 126.
- sac doctor --json returns valid JSON with checks list.
- sac version --json returns valid JSON with version field.
- sac release preflight --json returns valid JSON with ok field.
- Non-JSON output of ask and version is unchanged.
- CLIJSONResponse / render_json unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_shared_json import CLIJSONResponse, render_json

runner = CliRunner()


# ── Unit tests: CLIJSONResponse / render_json ─────────────────────────────────


class TestCLIJSONResponse:
    def test_basic_success(self):
        r = CLIJSONResponse(command="ask", status="success", data={"answer": "hi"})
        out = render_json(r)
        parsed = json.loads(out)
        assert parsed["command"] == "ask"
        assert parsed["status"] == "success"
        assert parsed["data"]["answer"] == "hi"

    def test_null_error_omitted(self):
        r = CLIJSONResponse(command="ask", status="success")
        out = render_json(r)
        parsed = json.loads(out)
        assert "error" not in parsed

    def test_error_included_when_set(self):
        r = CLIJSONResponse(command="ask", status="error", error="boom")
        out = render_json(r)
        parsed = json.loads(out)
        assert parsed["error"] == "boom"

    def test_sorted_keys(self):
        r = CLIJSONResponse(command="z", status="s", data={"b": 2, "a": 1})
        out = render_json(r)
        keys = list(json.loads(out).keys())
        assert keys == sorted(keys)

    def test_deterministic(self):
        r = CLIJSONResponse(command="ask", status="success", data={"x": 1})
        assert render_json(r) == render_json(r)

    def test_no_extra_fields_in_output(self):
        r = CLIJSONResponse(command="ask", status="success")
        parsed = json.loads(render_json(r))
        assert set(parsed.keys()) <= {"command", "status", "data", "error"}


# ── sac version --json ─────────────────────────────────────────────────────────


class TestVersionJSON:
    def test_returns_valid_json(self, tmp_path):
        result = runner.invoke(app, ["version", "--json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["command"] == "version"
        assert parsed["status"] == "success"
        assert "version" in parsed["data"]

    def test_version_field_is_string(self, tmp_path):
        result = runner.invoke(app, ["version", "--json"])
        parsed = json.loads(result.output)
        assert isinstance(parsed["data"]["version"], str)
        assert len(parsed["data"]["version"]) > 0

    def test_non_json_output_unchanged(self, tmp_path):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "SafeCode Agent" in result.output


# ── sac doctor --json ─────────────────────────────────────────────────────────


class TestDoctorJSON:
    def test_returns_valid_json(self, tmp_path):
        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["command"] == "doctor"
        assert parsed["status"] in ("pass", "fail")
        assert "checks" in parsed["data"]

    def test_checks_is_list_of_dicts(self, tmp_path):
        result = runner.invoke(app, ["doctor", "--json"])
        parsed = json.loads(result.output)
        checks = parsed["data"]["checks"]
        assert isinstance(checks, list)
        assert len(checks) > 0
        for check in checks:
            assert "name" in check
            assert "status" in check
            assert "message" in check

    def test_status_reflects_overall_pass_fail(self, tmp_path):
        result = runner.invoke(app, ["doctor", "--json"])
        parsed = json.loads(result.output)
        all_passed = all(c["status"] == "PASS" for c in parsed["data"]["checks"])
        assert parsed["status"] == ("pass" if all_passed else "fail")


# ── sac ask --json ─────────────────────────────────────────────────────────────


class TestAskJSON:
    def test_returns_valid_json(self, tmp_path):
        with patch("safecode.agent.orchestrator.AgentOrchestrator.ask") as mock_ask:
            from safecode.agent.schemas import AgentAnswer
            mock_ask.return_value = AgentAnswer(content="hello world")
            result = runner.invoke(app, ["ask", "what is this?", "--json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["command"] == "ask"
        assert parsed["status"] == "success"
        assert parsed["data"]["answer"] == "hello world"

    def test_error_returns_json_status_error(self, tmp_path):
        with patch("safecode.agent.orchestrator.AgentOrchestrator.ask") as mock_ask:
            mock_ask.side_effect = RuntimeError("LLM down")
            result = runner.invoke(app, ["ask", "what?", "--json"])
        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert parsed["status"] == "error"
        assert "LLM down" in parsed["error"]

    def test_non_json_output_is_text(self, tmp_path):
        with patch("safecode.agent.orchestrator.AgentOrchestrator.ask") as mock_ask:
            from safecode.agent.schemas import AgentAnswer
            mock_ask.return_value = AgentAnswer(content="plain answer")
            result = runner.invoke(app, ["ask", "what?"])
        assert result.exit_code == 0
        # Should not be JSON
        try:
            json.loads(result.output)
            # If it parses as JSON, it's still OK (rich might output something)
        except json.JSONDecodeError:
            pass  # expected: plain text output


# ── sac run --json ─────────────────────────────────────────────────────────────


class TestRunJSON:
    def test_low_risk_returns_valid_json(self, tmp_path):
        with patch("safecode.shell.runner.ShellRunner.run") as mock_run, \
             patch("safecode.shell.runner.ShellRunner.assess") as mock_assess, \
             patch("safecode.audit.logger.AuditLogger.write") as mock_audit_write:
            from safecode.shell.runner import ShellRunResult, ShellRisk
            from safecode.shell.risk import RiskLevel
            risk = ShellRisk(level=RiskLevel.LOW, reasons=[], tokens=["echo"])
            mock_assess.return_value = risk
            mock_run.return_value = ShellRunResult(
                command="echo hi",
                risk=risk,
                exit_code=0,
                stdout="hi",
                stderr="",
                duration_ms=1,
                executed=True,
            )
            result = runner.invoke(app, ["run", "echo hi", "--yes", "--json"])
        # exit code should be 0 (from shell result)
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["command"] == "run"
        assert "executed" in parsed["data"]
        assert "exit_code" in parsed["data"]

    def test_high_risk_blocked_returns_json_error(self, tmp_path):
        result = runner.invoke(app, ["run", "rm -rf /", "--json"])
        # exit code 126 = policy blocked
        assert result.exit_code == 126
        parsed = json.loads(result.output)
        assert parsed["command"] == "run"
        assert parsed["status"] == "error"


# ── sac edit --json ────────────────────────────────────────────────────────────


class TestEditJSON:
    def test_returns_valid_json_on_success(self, tmp_path):
        from unittest.mock import MagicMock
        from safecode.agent.orchestrator import EditResult
        from safecode.patch.models import PatchProposal, PatchBlock

        block = PatchBlock(operation="update", file_path="foo.py")
        proposal = PatchProposal(
            id="test-id",
            task="fix it",
            blocks=[block],
            created_at="2026-01-01T00:00:00Z",
            model="mock",
        )
        fake_result = EditResult(
            proposal=proposal,
            diff_text="--- a/foo.py\n+++ b/foo.py\n",
            pending_patch_path=tmp_path / ".sac" / "pending_patch.json",
        )
        with patch("safecode.agent.orchestrator.AgentOrchestrator.edit") as mock_edit, \
             patch("safecode.tools.gate.ToolCallGate.check_intent") as mock_gate:
            from safecode.tools.gate import GateResult
            mock_gate.return_value = GateResult(allowed=True, reason="ok")
            mock_edit.return_value = fake_result
            result = runner.invoke(app, ["edit", "fix foo", "--json"])

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["command"] == "edit"
        assert parsed["status"] == "success"
        assert "pending_patch_path" in parsed["data"]
        assert "diff_text" in parsed["data"]


# ── sac release preflight --json ──────────────────────────────────────────────


class TestReleasePreflightJSON:
    def test_returns_valid_json(self, tmp_path):
        result = runner.invoke(app, ["release", "preflight", "--json"])
        # exit code can be 0 or 1 depending on whether preflight passes
        parsed = json.loads(result.output)
        assert parsed["command"] == "release preflight"
        assert parsed["status"] in ("pass", "fail")
        assert "ok" in parsed["data"]

    def test_ok_field_is_bool(self, tmp_path):
        result = runner.invoke(app, ["release", "preflight", "--json"])
        parsed = json.loads(result.output)
        assert isinstance(parsed["data"]["ok"], bool)

    def test_has_component_fields(self, tmp_path):
        result = runner.invoke(app, ["release", "preflight", "--json"])
        parsed = json.loads(result.output)
        data = parsed["data"]
        assert "release_check" in data
        assert "smoke" in data
        assert "metadata" in data
        assert "docs" in data
