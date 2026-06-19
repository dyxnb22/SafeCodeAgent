"""Enterprise public contract snapshot helpers (v2.0)."""

from __future__ import annotations

from safecode.enterprise.evidence.export import EVIDENCE_SCHEMA_VERSION
from safecode.enterprise.trace.events import TRACE_SCHEMA_VERSION, TraceEvent, TraceEventType
from safecode.enterprise.trace.timeline import TIMELINE_SCHEMA_VERSION, RunTimeline
from safecode.enterprise.workflow.state import EnterpriseRunState, STATE_SCHEMA_VERSION

ENTERPRISE_CLI_COMMANDS: tuple[tuple[str, str], ...] = (
    ("enterprise", "retrieve"),
    ("workflow", "run"),
    ("workflow", "resume"),
    ("workflow", "gc"),
    ("approval", "list"),
    ("approval", "show"),
    ("approval", "approve"),
    ("approval", "reject"),
    ("approval", "request-evidence"),
    ("approval", "revoke"),
    ("trace", "export"),
    ("trace", "show"),
    ("eval", "run"),
    ("eval", "dashboard"),
    ("evidence", "export"),
)

EVIDENCE_MANIFEST_REQUIRED_KEYS = (
    "schema_version",
    "bundle_id",
    "run_id",
    "tenant_id",
    "task_type",
    "source_audit_chain_verified",
    "files",
)

EVIDENCE_BUNDLE_FILE_NAMES = (
    "manifest.json",
    "trace.jsonl",
    "state.json",
    "timeline.json",
    "citations.json",
    "approvals.json",
    "audit_chain.jsonl",
)

EVAL_BASELINE_CASE_KEYS = (
    "case_id",
    "passed",
    "metrics",
    "forbidden_behavior_triggered_eq",
)

EVAL_BASELINE_TOP_KEYS = (
    "suite",
    "date",
    "commit",
    "cases",
)


def enterprise_cli_contract() -> dict:
    return {
        "contract": "EnterpriseCLI",
        "contract_status": "supported",
        "commands": [
            {"group": group, "name": name} for group, name in ENTERPRISE_CLI_COMMANDS
        ],
    }


def trace_event_contract() -> dict:
    return {
        "contract": "EnterpriseTraceEvent",
        "contract_status": "supported",
        "schema_version": TRACE_SCHEMA_VERSION,
        "fields": sorted(TraceEvent.model_fields.keys()),
        "event_types": sorted(item.value for item in TraceEventType),
    }


def timeline_contract() -> dict:
    return {
        "contract": "EnterpriseRunTimeline",
        "contract_status": "supported",
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "fields": sorted(RunTimeline.model_fields.keys()),
    }


def evidence_export_contract() -> dict:
    return {
        "contract": "EnterpriseEvidenceExport",
        "contract_status": "supported",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "manifest_required_keys": list(EVIDENCE_MANIFEST_REQUIRED_KEYS),
        "bundle_file_names": list(EVIDENCE_BUNDLE_FILE_NAMES),
    }


def eval_baseline_contract() -> dict:
    return {
        "contract": "EnterpriseEvalBaseline",
        "contract_status": "supported",
        "top_level_keys": list(EVAL_BASELINE_TOP_KEYS),
        "case_keys": list(EVAL_BASELINE_CASE_KEYS),
    }


def workflow_state_contract() -> dict:
    return {
        "contract": "EnterpriseRunState",
        "contract_status": "supported",
        "schema_version": STATE_SCHEMA_VERSION,
        "fields": sorted(EnterpriseRunState.model_fields.keys()),
    }


def all_contracts() -> dict[str, dict]:
    return {
        "enterprise_cli": enterprise_cli_contract(),
        "trace_event": trace_event_contract(),
        "timeline": timeline_contract(),
        "evidence_export": evidence_export_contract(),
        "eval_baseline": eval_baseline_contract(),
        "workflow_state": workflow_state_contract(),
    }
