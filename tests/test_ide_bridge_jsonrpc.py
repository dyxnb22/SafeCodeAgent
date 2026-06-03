"""Tests for v3.5.0 localapi-jsonrpc and v3.5.1 vscode-extension-skeleton.

Verifies:
- process_request dispatches ask, report, edit, apply correctly.
- request_id is echoed in every response.
- Unknown method returns -32601 error.
- Parse error returns -32700 error.
- Missing required params return -32602 error.
- Invalid jsonrpc version returns -32600 error.
- process_request never raises.
- run_server reads from injected stdin and writes to injected stdout.
- IDE manifest includes jsonrpc_transport section with launch_command.
- IDE manifest includes safecode.apiJsonrpc command.
- JSONRPC contract version exported as string.
- sac api jsonrpc command is registered in the CLI.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.api.jsonrpc import (
    CONTRACT_VERSION,
    _SUPPORTED_METHODS,
    process_request,
    run_server,
)
from safecode.cli import app
from safecode.ide.manifest import _JSONRPC_CONTRACT_VERSION, render_manifest

runner = CliRunner()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _req(method: str, params: dict | None = None, req_id: int = 1) -> str:
    data: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        data["params"] = params
    return json.dumps(data)


def _parse(resp: dict) -> tuple[dict | None, dict | None]:
    return resp.get("result"), resp.get("error")


# ── Unit: process_request ──────────────────────────────────────────────────────


class TestProcessRequestAsk:
    def test_ask_dispatches_to_orchestrator(self, tmp_path):
        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.ask.return_value = "answer text"
            resp = process_request(_req("ask", {"question": "What is this?"}), tmp_path)
        result, error = _parse(resp)
        assert error is None
        assert result["answer"] == "answer text"

    def test_ask_echoes_request_id(self, tmp_path):
        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            MockOrch.return_value.ask.return_value = "x"
            resp = process_request(_req("ask", {"question": "q"}, req_id=42), tmp_path)
        assert resp["id"] == 42

    def test_ask_missing_question_returns_invalid_params(self, tmp_path):
        resp = process_request(_req("ask", {}), tmp_path)
        result, error = _parse(resp)
        assert result is None
        assert error["code"] == -32602

    def test_ask_empty_question_returns_invalid_params(self, tmp_path):
        resp = process_request(_req("ask", {"question": ""}), tmp_path)
        assert resp["error"]["code"] == -32602

    def test_ask_non_string_question_returns_invalid_params(self, tmp_path):
        resp = process_request(_req("ask", {"question": 123}), tmp_path)
        assert resp["error"]["code"] == -32602


class TestProcessRequestReport:
    def test_report_returns_markdown(self, tmp_path):
        with patch("safecode.api.jsonrpc.ReportRenderer") as MockRR:
            MockRR.return_value.render_markdown.return_value = "# Report"
            resp = process_request(_req("report"), tmp_path)
        result, error = _parse(resp)
        assert error is None
        assert result["report"] == "# Report"

    def test_report_echoes_id(self, tmp_path):
        with patch("safecode.api.jsonrpc.ReportRenderer") as MockRR:
            MockRR.return_value.render_markdown.return_value = ""
            resp = process_request(_req("report", req_id=99), tmp_path)
        assert resp["id"] == 99


class TestProcessRequestEdit:
    def _make_edit_result(self, patch_id: str = "p1") -> MagicMock:
        result = MagicMock()
        result.proposal.id = patch_id
        result.proposal.status = "pending"
        result.diff_text = "--- a\n+++ b\n"
        result.pending_patch_path = Path("/tmp/pending_patch.json")
        return result

    def test_edit_dispatches_to_orchestrator(self, tmp_path):
        edit_result = self._make_edit_result()
        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            MockOrch.return_value.edit.return_value = edit_result
            resp = process_request(_req("edit", {"task": "fix bug"}), tmp_path)
        result, error = _parse(resp)
        assert error is None
        assert result["patch_id"] == "p1"
        assert result["status"] == "pending"
        assert "diff" in result
        assert "pending_patch_path" in result

    def test_edit_missing_task_returns_invalid_params(self, tmp_path):
        resp = process_request(_req("edit", {}), tmp_path)
        assert resp["error"]["code"] == -32602

    def test_edit_empty_task_returns_invalid_params(self, tmp_path):
        resp = process_request(_req("edit", {"task": ""}), tmp_path)
        assert resp["error"]["code"] == -32602


class TestProcessRequestApply:
    def _make_apply_mocks(self):
        preview = MagicMock()
        preview.proposal.id = "p1"

        result = MagicMock()
        result.proposal.id = "p1"
        result.files = ["src/app.py"]
        result.checkpoint.id = "ckpt-abc"

        return preview, result

    def test_apply_dispatches_to_orchestrator(self, tmp_path):
        preview, result = self._make_apply_mocks()
        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.preview_apply.return_value = preview
            instance.apply.return_value = result
            resp = process_request(_req("apply"), tmp_path)
        r, error = _parse(resp)
        assert error is None
        assert r["patch_id"] == "p1"
        assert r["files"] == ["src/app.py"]
        assert r["checkpoint_id"] == "ckpt-abc"

    def test_apply_file_not_found_returns_internal_error(self, tmp_path):
        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            MockOrch.return_value.preview_apply.side_effect = FileNotFoundError("no pending")
            resp = process_request(_req("apply"), tmp_path)
        assert resp["error"]["code"] == -32603

    def test_apply_generic_error_returns_internal_error(self, tmp_path):
        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            MockOrch.return_value.preview_apply.side_effect = RuntimeError("boom")
            resp = process_request(_req("apply"), tmp_path)
        assert resp["error"]["code"] == -32603
        assert "boom" not in resp["error"]["message"]


class TestProcessRequestErrorCases:
    def test_unknown_method_returns_32601(self, tmp_path):
        resp = process_request(_req("unknown_method"), tmp_path)
        assert resp["error"]["code"] == -32601

    def test_parse_error_returns_32700(self, tmp_path):
        resp = process_request("{invalid json", tmp_path)
        assert resp["error"]["code"] == -32700

    def test_parse_error_id_is_none(self, tmp_path):
        resp = process_request("not json", tmp_path)
        assert resp["id"] is None

    def test_wrong_jsonrpc_version_returns_32600(self, tmp_path):
        line = json.dumps({"jsonrpc": "1.0", "id": 1, "method": "ask"})
        resp = process_request(line, tmp_path)
        assert resp["error"]["code"] == -32600

    def test_missing_jsonrpc_field_returns_32600(self, tmp_path):
        line = json.dumps({"id": 1, "method": "ask"})
        resp = process_request(line, tmp_path)
        assert resp["error"]["code"] == -32600

    def test_missing_method_returns_32600(self, tmp_path):
        line = json.dumps({"jsonrpc": "2.0", "id": 1})
        resp = process_request(line, tmp_path)
        assert resp["error"]["code"] == -32600

    def test_non_dict_request_returns_32600(self, tmp_path):
        line = json.dumps([1, 2, 3])
        resp = process_request(line, tmp_path)
        assert resp["error"]["code"] == -32600

    def test_process_request_never_raises(self, tmp_path):
        # Even completely malformed input should not raise
        for bad in ["", "   ", "null", "[]", "{}", "true"]:
            resp = process_request(bad, tmp_path)
            assert isinstance(resp, dict)

    def test_jsonrpc_version_in_all_responses(self, tmp_path):
        resp = process_request("{invalid}", tmp_path)
        assert resp["jsonrpc"] == "2.0"

    def test_id_echoed_in_error(self, tmp_path):
        line = json.dumps({"jsonrpc": "2.0", "id": 77, "method": "nonexistent"})
        resp = process_request(line, tmp_path)
        assert resp["id"] == 77


class TestSupportedMethods:
    def test_supported_methods_frozen(self):
        assert isinstance(_SUPPORTED_METHODS, frozenset)

    def test_expected_methods_present(self):
        assert "ask" in _SUPPORTED_METHODS
        assert "report" in _SUPPORTED_METHODS
        assert "edit" in _SUPPORTED_METHODS
        assert "apply" in _SUPPORTED_METHODS

    def test_no_extra_methods_exposed(self):
        # only the four documented methods should be in the set
        assert _SUPPORTED_METHODS == frozenset({"ask", "report", "edit", "apply"})


# ── Unit: run_server ───────────────────────────────────────────────────────────


class TestRunServer:
    def test_run_server_processes_ask_from_stdin(self, tmp_path):
        req = _req("ask", {"question": "q"}) + "\n"
        stdin = io.StringIO(req)
        stdout = io.StringIO()

        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            MockOrch.return_value.ask.return_value = "the answer"
            run_server(tmp_path, stdin=stdin, stdout=stdout)

        output = stdout.getvalue()
        resp = json.loads(output.strip())
        assert resp["result"]["answer"] == "the answer"

    def test_run_server_skips_blank_lines(self, tmp_path):
        lines = "\n\n" + _req("report") + "\n\n"
        stdin = io.StringIO(lines)
        stdout = io.StringIO()

        with patch("safecode.api.jsonrpc.ReportRenderer") as MockRR:
            MockRR.return_value.render_markdown.return_value = "rpt"
            run_server(tmp_path, stdin=stdin, stdout=stdout)

        lines_out = [l for l in stdout.getvalue().splitlines() if l.strip()]
        assert len(lines_out) == 1

    def test_run_server_handles_multiple_requests(self, tmp_path):
        r1 = _req("ask", {"question": "q1"}, req_id=1)
        r2 = _req("ask", {"question": "q2"}, req_id=2)
        stdin = io.StringIO(r1 + "\n" + r2 + "\n")
        stdout = io.StringIO()

        with patch("safecode.api.jsonrpc.AgentOrchestrator") as MockOrch:
            MockOrch.return_value.ask.side_effect = ["a1", "a2"]
            run_server(tmp_path, stdin=stdin, stdout=stdout)

        responses = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
        assert len(responses) == 2
        assert responses[0]["id"] == 1
        assert responses[1]["id"] == 2

    def test_run_server_output_is_newline_delimited(self, tmp_path):
        stdin = io.StringIO(_req("report") + "\n")
        stdout = io.StringIO()

        with patch("safecode.api.jsonrpc.ReportRenderer") as MockRR:
            MockRR.return_value.render_markdown.return_value = ""
            run_server(tmp_path, stdin=stdin, stdout=stdout)

        raw = stdout.getvalue()
        assert raw.endswith("\n")

    def test_run_server_uses_sorted_keys(self, tmp_path):
        stdin = io.StringIO(_req("report") + "\n")
        stdout = io.StringIO()

        with patch("safecode.api.jsonrpc.ReportRenderer") as MockRR:
            MockRR.return_value.render_markdown.return_value = ""
            run_server(tmp_path, stdin=stdin, stdout=stdout)

        raw = stdout.getvalue().strip()
        parsed = json.loads(raw)
        keys = list(parsed.keys())
        assert keys == sorted(keys)


# ── IDE manifest: v3.5.1 jsonrpc launch metadata ───────────────────────────────


class TestIDEManifestJsonrpcMetadata:
    def test_manifest_has_jsonrpc_transport(self):
        data = json.loads(render_manifest())
        assert "jsonrpc_transport" in data

    def test_jsonrpc_launch_command(self):
        data = json.loads(render_manifest())
        cmd = data["jsonrpc_transport"]["launch_command"]
        assert cmd == ["sac", "api", "jsonrpc"]

    def test_jsonrpc_protocol_is_2_0(self):
        data = json.loads(render_manifest())
        assert data["jsonrpc_transport"]["protocol"] == "json-rpc-2.0"

    def test_jsonrpc_transport_is_stdio(self):
        data = json.loads(render_manifest())
        assert data["jsonrpc_transport"]["transport"] == "stdio"

    def test_jsonrpc_supported_methods(self):
        data = json.loads(render_manifest())
        methods = data["jsonrpc_transport"]["supported_methods"]
        assert set(methods) == {"ask", "report", "edit", "apply"}

    def test_jsonrpc_experimental_note(self):
        data = json.loads(render_manifest())
        note = data["jsonrpc_transport"]["note"].lower()
        assert "experimental" in note

    def test_manifest_includes_api_jsonrpc_command(self):
        data = json.loads(render_manifest())
        ids = [c["id"] for c in data["commands"]]
        assert "safecode.apiJsonrpc" in ids

    def test_manifest_includes_open_diff_command(self):
        data = json.loads(render_manifest())
        ids = [c["id"] for c in data["commands"]]
        assert "safecode.openDiff" in ids

    def test_manifest_has_pending_diff_targets(self):
        data = json.loads(render_manifest())
        assert "pending_diff_targets" in data
        assert "open_diff_command" in data["pending_diff_targets"]

    def test_contract_version_is_string(self):
        assert isinstance(_JSONRPC_CONTRACT_VERSION, str)

    def test_contract_version_exported_from_module(self):
        assert CONTRACT_VERSION == _JSONRPC_CONTRACT_VERSION

    def test_manifest_deterministic(self):
        assert render_manifest() == render_manifest()


# ── CLI: sac api jsonrpc ───────────────────────────────────────────────────────


class TestCLIApiJsonrpc:
    def test_api_jsonrpc_command_registered(self):
        result = runner.invoke(app, ["api", "--help"])
        assert result.exit_code == 0
        assert "jsonrpc" in result.output.lower()

    def test_api_jsonrpc_help(self):
        result = runner.invoke(app, ["api", "jsonrpc", "--help"])
        assert result.exit_code == 0
        assert "experimental" in result.output.lower()

    def test_api_jsonrpc_reads_stdin_and_writes_stdout(self, tmp_path):
        req_line = _req("report") + "\n"

        with patch("safecode.api.jsonrpc.run_server") as mock_run:
            mock_run.return_value = None
            result = runner.invoke(
                app,
                ["api", "jsonrpc", "--project-root", str(tmp_path)],
                input=req_line,
            )
        assert result.exit_code == 0
        mock_run.assert_called_once()
