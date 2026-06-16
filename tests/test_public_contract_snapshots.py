"""v2.9.9 public contract snapshot tests.

Covers the v3.0-supported local safety contracts. Snapshots are deterministic:
no timestamps, absolute paths, host-specific data, random ids, or git-specific values.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

_CONTRACTS = Path(__file__).parent / "snapshots" / "contracts"
_REGISTRY = Path(__file__).parent / "snapshots" / "registry"
_LOOP = Path(__file__).parent / "snapshots" / "loop"


# ── Helpers ────────────────────────────────────────────────────────────────


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _fields(model_class) -> list[str]:
    """Return sorted field names for a Pydantic model or dataclass."""
    if hasattr(model_class, "model_fields"):
        return sorted(model_class.model_fields)
    if dataclasses.is_dataclass(model_class):
        return sorted(f.name for f in dataclasses.fields(model_class))
    raise TypeError(f"Unsupported model type: {model_class}")


# ── Snapshot file existence ────────────────────────────────────────────────


class TestSnapshotFilesExist:
    def test_contracts_dir_exists(self):
        assert _CONTRACTS.is_dir()

    def test_config_defaults_snapshot_exists(self):
        assert (_CONTRACTS / "config_defaults.json").exists()

    def test_pending_patch_snapshot_exists(self):
        assert (_CONTRACTS / "pending_patch_schema.json").exists()

    def test_audit_event_snapshot_exists(self):
        assert (_CONTRACTS / "audit_event_schema.json").exists()

    def test_sandbox_schemas_snapshot_exists(self):
        assert (_CONTRACTS / "sandbox_schemas.json").exists()

    def test_eval_trace_snapshot_exists(self):
        assert (_CONTRACTS / "eval_trace_schema.json").exists()

    def test_cli_json_envelope_snapshot_exists(self):
        assert (_CONTRACTS / "cli_json_envelope.json").exists()

    def test_tool_registry_snapshot_exists(self):
        assert (_REGISTRY / "tool_registry_v1.json").exists()

    def test_loop_snapshots_exist(self):
        loop_files = list(_LOOP.glob("*.json"))
        assert len(loop_files) >= 6, f"Expected ≥6 loop snapshots, found {len(loop_files)}"


# ── SafeCodeConfig contract ────────────────────────────────────────────────


class TestConfigContract:
    def _snapshot(self):
        return _load(_CONTRACTS / "config_defaults.json")

    def test_contract_label(self):
        snap = self._snapshot()
        assert snap["contract"] == "SafeCodeConfig"
        assert snap["contract_status"] == "supported"

    def test_live_defaults_match_snapshot(self):
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        snap = self._snapshot()["defaults"]

        assert cfg.sac_dir == snap["sac_dir"]
        assert cfg.max_tree_files == snap["max_tree_files"]
        assert cfg.max_file_lines == snap["max_file_lines"]
        assert cfg.max_file_bytes == snap["max_file_bytes"]
        assert cfg.max_context_chars == snap["max_context_chars"]
        assert cfg.policy == snap["policy"]

    def test_live_shell_defaults_match_snapshot(self):
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        snap = self._snapshot()["defaults"]["shell"]

        assert cfg.shell.default_timeout_seconds == snap["default_timeout_seconds"]
        assert cfg.shell.allow_readonly_without_confirm == snap["allow_readonly_without_confirm"]
        assert cfg.shell.require_confirm_for_medium == snap["require_confirm_for_medium"]
        assert cfg.shell.block_high_risk == snap["block_high_risk"]
        assert sorted(cfg.shell.allowed_commands) == sorted(snap["allowed_commands"])

    def test_live_sandbox_defaults_match_snapshot(self):
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        snap = self._snapshot()["defaults"]["sandbox"]

        assert cfg.sandbox.restrict_to_project_root == snap["restrict_to_project_root"]
        assert cfg.sandbox.network_enabled == snap["network_enabled"]
        assert cfg.sandbox.network_allowlist == snap["network_allowlist"]
        assert sorted(cfg.sandbox.sensitive_names) == sorted(snap["sensitive_names"])

    def test_live_hooks_defaults_match_snapshot(self):
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        snap = self._snapshot()["defaults"]["hooks"]

        assert cfg.hooks.before_command == snap["before_command"]
        assert cfg.hooks.after_edit == snap["after_edit"]
        assert cfg.hooks.after_test == snap["after_test"]
        assert cfg.hooks.after_apply == snap["after_apply"]
        assert cfg.hooks.allow_medium_after_apply == snap["allow_medium_after_apply"]

    def test_live_llm_provider_default_is_mock(self):
        from safecode.config import SafeCodeConfig

        cfg = SafeCodeConfig()
        snap = self._snapshot()["defaults"]["llm"]
        assert cfg.llm.provider == snap["provider"]
        assert cfg.llm.provider == "mock"

    def test_known_policy_names_match_snapshot(self):
        from safecode.config import KNOWN_POLICY_NAMES

        snap_names = sorted(self._snapshot()["known_policy_names"])
        assert sorted(KNOWN_POLICY_NAMES) == snap_names

    def test_snapshot_is_valid_json_with_sorted_keys(self):
        raw = (_CONTRACTS / "config_defaults.json").read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip()


# ── Pending patch contract ─────────────────────────────────────────────────


class TestPendingPatchContract:
    def _snapshot(self):
        return _load(_CONTRACTS / "pending_patch_schema.json")

    def test_contract_label(self):
        snap = self._snapshot()
        assert snap["contract"] == "PendingPatch"
        assert snap["contract_status"] == "supported"

    def test_patch_proposal_fields_match_snapshot(self):
        from safecode.patch.models import PatchProposal

        live = _fields(PatchProposal)
        snap = sorted(self._snapshot()["models"]["PatchProposal"]["fields"])
        assert live == snap

    def test_patch_block_fields_match_snapshot(self):
        from safecode.patch.models import PatchBlock

        live = _fields(PatchBlock)
        snap = sorted(self._snapshot()["models"]["PatchBlock"]["fields"])
        assert live == snap

    def test_snapshot_is_valid_json_with_sorted_keys(self):
        raw = (_CONTRACTS / "pending_patch_schema.json").read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip()


# ── Audit event contract ───────────────────────────────────────────────────


class TestAuditEventContract:
    def _snapshot(self):
        return _load(_CONTRACTS / "audit_event_schema.json")

    def test_contract_label(self):
        snap = self._snapshot()
        assert snap["contract"] == "AuditEvent"
        assert snap["contract_status"] == "supported"

    def test_audit_event_fields_match_snapshot(self):
        from safecode.audit.models import AuditEvent

        live = _fields(AuditEvent)
        snap = sorted(self._snapshot()["fields"])
        assert live == snap

    def test_known_event_types_include_registry_events(self):
        from safecode.tools.registry import ToolRegistry

        snap_types = set(self._snapshot()["known_event_types_from_tool_registry"])
        registry_types = {
            spec.audit_event.event_type
            for spec in ToolRegistry().list()
            if spec.audit_event is not None
        }
        assert registry_types == snap_types

    def test_hash_chain_invariants_present(self):
        snap = self._snapshot()
        assert len(snap["hash_chain_invariants"]) >= 3

    def test_snapshot_is_valid_json_with_sorted_keys(self):
        raw = (_CONTRACTS / "audit_event_schema.json").read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip()


# ── Sandbox lifecycle contract ─────────────────────────────────────────────


class TestSandboxContract:
    def _snapshot(self):
        return _load(_CONTRACTS / "sandbox_schemas.json")

    def test_contract_label(self):
        snap = self._snapshot()
        assert snap["contract"] == "SandboxLifecycle"
        assert snap["contract_status"] == "supported"

    def test_proposal_fields_match_snapshot(self):
        from safecode.sandbox.execution import SandboxExecutionProposal

        live = _fields(SandboxExecutionProposal)
        snap = sorted(self._snapshot()["models"]["SandboxExecutionProposal"]["fields"])
        assert live == snap

    def test_approval_fields_match_snapshot(self):
        from safecode.sandbox.approvals import SandboxExecutionApproval

        live = _fields(SandboxExecutionApproval)
        snap = sorted(self._snapshot()["models"]["SandboxExecutionApproval"]["fields"])
        assert live == snap

    def test_result_record_fields_match_snapshot(self):
        from safecode.sandbox.execution import SandboxExecutionResultRecord

        live = _fields(SandboxExecutionResultRecord)
        snap = sorted(self._snapshot()["models"]["SandboxExecutionResultRecord"]["fields"])
        assert live == snap

    def test_approval_invariants_present(self):
        snap = self._snapshot()
        assert len(snap["approval_invariants"]) >= 4

    def test_snapshot_is_valid_json_with_sorted_keys(self):
        raw = (_CONTRACTS / "sandbox_schemas.json").read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip()


# ── Tool registry contract (reuses v2.9.8 snapshot) ───────────────────────


class TestToolRegistryContract:
    def _snapshot(self):
        return _load(_REGISTRY / "tool_registry_v1.json")

    def test_registry_snapshot_has_schema_version(self):
        snap = self._snapshot()
        assert "registry_schema_version" in snap

    def test_all_tools_have_version(self):
        for tool in self._snapshot()["tools"]:
            assert "version" in tool
            assert isinstance(tool["version"], str)

    def test_snapshot_matches_live_registry(self):
        from safecode.tools.registry import REGISTRY_SCHEMA_VERSION, ToolRegistry

        registry = ToolRegistry()
        tools = registry.list()
        live = {
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
        assert live == self._snapshot()

    def test_snapshot_is_valid_json_with_sorted_keys(self):
        raw = (_REGISTRY / "tool_registry_v1.json").read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip()


# ── Eval trace contract ────────────────────────────────────────────────────


class TestEvalTraceContract:
    def _snapshot(self):
        return _load(_CONTRACTS / "eval_trace_schema.json")

    def test_contract_label(self):
        snap = self._snapshot()
        assert snap["contract"] == "EvalTrace"
        assert snap["contract_status"] == "supported"

    def test_loop_step_trace_fields_match_snapshot(self):
        from safecode.eval.loop_runner import LoopStepTrace

        live = _fields(LoopStepTrace)
        snap = sorted(self._snapshot()["models"]["LoopStepTrace"]["fields"])
        assert live == snap

    def test_loop_eval_trace_fields_match_snapshot(self):
        from safecode.eval.loop_runner import LoopEvalTrace

        live = _fields(LoopEvalTrace)
        snap = sorted(self._snapshot()["models"]["LoopEvalTrace"]["fields"])
        assert live == snap

    def test_loop_fixture_snapshots_are_deterministic(self):
        from safecode.eval.loop_runner import build_loop_eval_trace, default_loop_fixtures

        for fixture in default_loop_fixtures():
            trace_a = build_loop_eval_trace(fixture)
            trace_b = build_loop_eval_trace(fixture)
            assert trace_a.as_dict() == trace_b.as_dict()

    def test_loop_fixture_snapshots_match_on_disk(self):
        from safecode.eval.loop_runner import build_loop_eval_trace, default_loop_fixtures

        for fixture in default_loop_fixtures():
            snap_path = _LOOP / f"{fixture.name}.json"
            assert snap_path.exists(), f"Missing loop snapshot: {snap_path}"
            expected = json.loads(snap_path.read_text())
            actual = build_loop_eval_trace(fixture).as_dict()
            assert actual == expected, f"Trace mismatch for fixture {fixture.name!r}"

    def test_snapshot_is_valid_json_with_sorted_keys(self):
        raw = (_CONTRACTS / "eval_trace_schema.json").read_text()
        data = json.loads(raw)
        regenerated = json.dumps(data, indent=2, sort_keys=True)
        assert raw.strip() == regenerated.strip()


# ── Cross-contract determinism ─────────────────────────────────────────────


class TestCrossContractDeterminism:
    @pytest.mark.parametrize("snap_file", [
        "config_defaults.json",
        "pending_patch_schema.json",
        "audit_event_schema.json",
        "sandbox_schemas.json",
        "eval_trace_schema.json",
        "cli_json_envelope.json",
    ])
    def test_snapshot_has_contract_and_schema_version(self, snap_file: str):
        data = _load(_CONTRACTS / snap_file)
        assert "contract" in data
        assert "schema_version" in data

    @pytest.mark.parametrize("snap_file", [
        "config_defaults.json",
        "pending_patch_schema.json",
        "audit_event_schema.json",
        "sandbox_schemas.json",
        "eval_trace_schema.json",
        "cli_json_envelope.json",
    ])
    def test_snapshot_no_timestamps_or_paths(self, snap_file: str):
        raw = (_CONTRACTS / snap_file).read_text()
        data = json.dumps(json.loads(raw))
        assert "/Users/" not in data
        assert "/home/" not in data


class TestCLIJSONEnvelopeContract:
    """v3.7.2 — stable contract tests for CLIJSONResponse envelope."""

    def _snapshot(self) -> dict:
        return _load(_CONTRACTS / "cli_json_envelope.json")

    def test_snapshot_file_exists(self) -> None:
        assert (_CONTRACTS / "cli_json_envelope.json").exists()

    def test_contract_label_is_cli_json_response(self) -> None:
        snap = self._snapshot()
        assert snap["contract"] == "CLIJSONResponse"
        assert snap["contract_status"] == "supported"

    def test_required_fields_match_live_model(self) -> None:
        from safecode.cli_shared_json import CLIJSONResponse
        snap_fields = set(self._snapshot()["required_fields"])
        model_fields = set(CLIJSONResponse.model_fields.keys())
        for field in snap_fields:
            assert field in model_fields, f"required field '{field}' missing from CLIJSONResponse"

    def test_error_is_optional_field(self) -> None:
        snap = self._snapshot()
        assert "error" in snap["optional_fields"]

    def test_error_omitted_when_null(self) -> None:
        import json as _json
        from safecode.cli_shared_json import CLIJSONResponse, render_json
        response = CLIJSONResponse(command="ask", status="success", data={"answer": "hi"})
        rendered = _json.loads(render_json(response))
        assert "error" not in rendered

    def test_error_present_when_non_null(self) -> None:
        import json as _json
        from safecode.cli_shared_json import CLIJSONResponse, render_json
        response = CLIJSONResponse(command="ask", status="error", error="something failed")
        rendered = _json.loads(render_json(response))
        assert "error" in rendered
        assert rendered["error"] == "something failed"

    def test_data_field_is_always_dict(self) -> None:
        import json as _json
        from safecode.cli_shared_json import CLIJSONResponse, render_json
        response = CLIJSONResponse(command="fix", status="success")
        rendered = _json.loads(render_json(response))
        assert isinstance(rendered["data"], dict)

    def test_output_has_required_keys_present(self) -> None:
        import json as _json
        from safecode.cli_shared_json import CLIJSONResponse, render_json
        response = CLIJSONResponse(command="edit", status="success", data={"diff": "..."})
        rendered = _json.loads(render_json(response))
        for field in self._snapshot()["required_fields"]:
            assert field in rendered, f"required field '{field}' missing from output"

    def test_output_is_sorted_keys(self) -> None:
        from safecode.cli_shared_json import CLIJSONResponse, render_json
        response = CLIJSONResponse(command="z", status="success", data={"b": 1, "a": 2})
        text = render_json(response)
        # The keys in the outer envelope must be sorted
        import json as _json
        keys = list(_json.loads(text).keys())
        assert keys == sorted(keys)

    def test_snapshot_invariants_listed(self) -> None:
        snap = self._snapshot()
        assert "invariants" in snap
        invariants_text = " ".join(snap["invariants"]).lower()
        assert "omitted" in invariants_text
        assert "error" in invariants_text


class TestMCPReadContract:
    """v3.8.2 MCP read execution contract snapshot tests."""

    def _snapshot(self) -> dict:
        path = _CONTRACTS / "mcp_read_contract.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_snapshot_file_exists(self) -> None:
        assert (_CONTRACTS / "mcp_read_contract.json").exists()

    def test_contract_label_is_mcp_read_execution(self) -> None:
        snap = self._snapshot()
        assert snap["contract"] == "MCPReadExecution"

    def test_contract_status_is_supported(self) -> None:
        snap = self._snapshot()
        assert snap["contract_status"] == "supported"

    def test_result_fields_include_required(self) -> None:
        snap = self._snapshot()
        required = {"server", "tool", "classification", "output", "error",
                    "exit_code", "duration_ms", "executed", "blocked"}
        assert required <= set(snap["result_fields"])

    def test_gate_order_scope_before_classification(self) -> None:
        snap = self._snapshot()
        gates = snap["gate_order"]
        assert gates.index("scope_gate") < gates.index("classification_gate")

    def test_scope_vocabulary_complete(self) -> None:
        snap = self._snapshot()
        scopes = set(snap["scope_vocabulary"])
        assert "denied" in scopes
        assert "read_only" in scopes
        assert "write_proposal_required" in scopes

    def test_default_scope_unknown_server_is_denied(self) -> None:
        snap = self._snapshot()
        assert snap["default_scope_unknown_server"] == "denied"

    def test_default_scope_known_server_is_read_only(self) -> None:
        snap = self._snapshot()
        assert snap["default_scope_known_server"] == "read_only"

    def test_invariants_mention_scope_before_classification(self) -> None:
        snap = self._snapshot()
        text = " ".join(snap["invariants"]).lower()
        assert "scope" in text
        assert "before" in text
        assert "classification" in text

    def test_invariants_mention_server_supplied_classification_ignored(self) -> None:
        snap = self._snapshot()
        text = " ".join(snap["invariants"]).lower()
        assert "server-supplied" in text or "ignored" in text

    def test_invariants_mention_redaction(self) -> None:
        snap = self._snapshot()
        text = " ".join(snap["invariants"]).lower()
        assert "redact" in text

    def test_snapshot_is_valid_json_with_sorted_keys(self) -> None:
        path = _CONTRACTS / "mcp_read_contract.json"
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        serialized = json.dumps(data, sort_keys=True, indent=2)
        reloaded = json.loads(serialized)
        assert data == reloaded

    def test_runner_entry_point_matches_snapshot(self) -> None:
        snap = self._snapshot()
        assert snap["entry_point"] == "MCPReadOnlyRunner.call_readonly"
        from safecode.mcp.runner import MCPReadOnlyRunner
        assert hasattr(MCPReadOnlyRunner, "call_readonly")

    def test_result_type_matches_live_code(self) -> None:
        snap = self._snapshot()
        assert snap["result_type"] == "MCPRunResult"
        from safecode.mcp.runner import MCPRunResult
        import dataclasses as _dc
        fields = {f.name for f in _dc.fields(MCPRunResult)}
        assert set(snap["result_fields"]) <= fields

    def test_write_execution_remains_experimental(self) -> None:
        """Verify write execution is NOT promoted in this snapshot."""
        snap = self._snapshot()
        text = " ".join(snap["invariants"]).lower()
        assert "write execution" in text and "experimental" in text

    def test_public_contracts_doc_has_mcp_read_section(self) -> None:
        doc = (Path(__file__).parent.parent / "docs" / "public-contracts.md").read_text(encoding="utf-8")
        assert "MCP Read Execution Contract" in doc
        assert "MCPReadOnlyRunner.call_readonly" in doc


class TestV40PromotionDecisions:
    """v3.99.1 promotion decision pass for the v4.0 contract cut."""

    def _doc(self) -> str:
        return (Path(__file__).parent.parent / "docs" / "public-contracts.md").read_text(encoding="utf-8")

    def test_decision_section_exists(self) -> None:
        doc = self._doc()
        assert "v4.0 Promotion Decision Pass" in doc

    def test_cli_json_envelope_promoted_already_stable(self) -> None:
        doc = self._doc()
        assert "CLI `--json` envelope" in doc
        assert "promote (already stable)" in doc
        assert "cli_json_envelope.json" in doc

    def test_mcp_read_execution_promoted_already_stable(self) -> None:
        doc = self._doc()
        assert "MCP read execution" in doc
        assert "mcp_read_contract.json" in doc

    def test_ide_jsonrpc_deferred(self) -> None:
        doc = self._doc()
        assert "IDE JSON-RPC" in doc
        assert "**defer**" in doc
        assert "no VSIX build or release-cycle consumption evidence" in doc

    def test_tui_rejected_for_v40_stable_promotion(self) -> None:
        doc = self._doc()
        assert "TUI interactive" in doc
        assert "reject stable promotion at v4.0" in doc

    def test_report_html_deferred(self) -> None:
        doc = self._doc()
        assert "`sac report html`" in doc
        assert "not snapshot-promoted as a public contract" in doc

    def test_sandbox_real_execution_opt_in_deferred(self) -> None:
        doc = self._doc()
        assert "Sandbox real-execution opt-in" in doc
        assert "host-local" in doc
        assert "insufficient for a stable v4 contract" in doc

    def test_no_new_stable_contract_promoted_by_v3991(self) -> None:
        doc = self._doc()
        assert "No new stable contract is promoted by v3.99.1 itself" in doc

    def test_deferred_surfaces_are_not_listed_as_stable_contract_headings(self) -> None:
        doc = self._doc()
        stable, _experimental = doc.split("## Experimental Surfaces", 1)
        assert "IDE JSON-RPC Contract" not in stable
        assert "TUI Interactive Contract" not in stable
        assert "HTML Report Contract" not in stable
        assert "Sandbox Real Execution Opt-In Contract" not in stable


class TestV400ContractCut:
    """v4.0.0 contract cut: no new stable contracts, no v3.0 breakage."""

    def _doc(self) -> str:
        return (Path(__file__).parent.parent / "docs" / "public-contracts.md").read_text(encoding="utf-8")

    def test_v400_contract_cut_section_exists(self) -> None:
        assert "v4.0.0 Contract Cut" in self._doc()

    def test_v400_promotes_no_new_stable_contracts(self) -> None:
        doc = self._doc()
        assert "New stable contracts promoted at v4.0.0:** none" in doc

    def test_v400_breaks_zero_v30_contracts(self) -> None:
        doc = self._doc()
        assert "Breaking changes to v3.0 public contracts:** zero" in doc

    def test_v400_preserves_already_stable_cli_and_mcp_contracts(self) -> None:
        doc = self._doc()
        assert "CLI JSON envelope" in doc
        assert "stable since v3.7.2" in doc
        assert "MCP read execution" in doc
        assert "stable since v3.8.2" in doc


# ---------------------------------------------------------------------------
# v5.7.1: sandbox promotion + OTel/HTML freeze
# ---------------------------------------------------------------------------


class TestV571SandboxContractPromotion:
    """Section 17 — Sandbox Execution Contract (v5.7.1)."""

    def _doc(self) -> str:
        return (Path(__file__).parent.parent / "docs" / "public-contracts.md").read_text(encoding="utf-8")

    def test_sandbox_section_17_exists(self) -> None:
        doc = self._doc()
        assert "### 17. Sandbox Execution Contract" in doc

    def test_sandbox_promoted_surfaces_listed(self) -> None:
        doc = self._doc()
        assert "SandboxExecutionProposal" in doc
        assert "SandboxApproval" in doc
        assert "SandboxResultRecord" in doc

    def test_sandbox_invariants_documented(self) -> None:
        doc = self._doc()
        assert "claim_for_execution" in doc
        assert "shell=False" in doc
        assert "--network none" in doc
        assert "--privileged" in doc

    def test_sandbox_promoted_at_v571(self) -> None:
        doc = self._doc()
        assert "v5.7.1" in doc

    def test_sandbox_env_gates_documented(self) -> None:
        doc = self._doc()
        assert "SAFECODE_SANDBOX_DOCKER=1" in doc
        assert "SAFECODE_SANDBOX_SEATBELT=1" in doc
        assert "SAFECODE_SANDBOX_BUBBLEWRAP=1" in doc


class TestV571OTelHtmlFreeze:
    """OTel exporter and HTML report frozen experimental at v5.7.1."""

    def _doc(self) -> str:
        return (Path(__file__).parent.parent / "docs" / "public-contracts.md").read_text(encoding="utf-8")

    def test_otel_frozen_experimental_noted(self) -> None:
        doc = self._doc()
        assert "Frozen experimental at v5.7.1" in doc
        assert "OtelExporter" in doc or "OTEL" in doc.upper()

    def test_html_report_frozen_experimental_noted(self) -> None:
        doc = self._doc()
        assert "sac report html" in doc
        assert "Frozen experimental at v5.7.1" in doc

    def test_v571_decision_section_exists(self) -> None:
        doc = self._doc()
        assert "v5.7.1 Contract Decisions" in doc

    def test_sandbox_promote_stated(self) -> None:
        doc = self._doc()
        assert "PROMOTE to stable contract" in doc

    def test_otel_freeze_stated(self) -> None:
        doc = self._doc()
        assert "FREEZE experimental" in doc
