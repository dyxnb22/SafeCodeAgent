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
    ])
    def test_snapshot_no_timestamps_or_paths(self, snap_file: str):
        raw = (_CONTRACTS / snap_file).read_text()
        data = json.dumps(json.loads(raw))
        assert "/Users/" not in data
        assert "/home/" not in data
