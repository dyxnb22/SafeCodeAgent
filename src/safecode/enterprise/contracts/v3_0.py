"""Enterprise GA v3.0 public contract snapshot helpers (v3.0.1-T1)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from safecode.enterprise.api.contracts import CONTRACT_STATUS, load_openapi_contract
from safecode.enterprise.contracts.snapshot import all_contracts
from safecode.enterprise.contracts.v2_1 import assert_snapshot_safe, team_server_v2_1_contract
from safecode.enterprise.contracts.v2_3 import operator_console_v2_3_contract

GA_VERSION = "3.0.0"
API_PATH_PREFIX = "/v2"
MIGRATION_FROM = "v2.0.0-rc"
DECISION_REFS: tuple[str, ...] = ("D29",)

SUPPORTED_SURFACES: tuple[str, ...] = (
    "enterprise_cli",
    "team_server_api_v2",
    "operator_console",
    "trace_event",
    "timeline",
    "evidence_export",
    "eval_baseline",
    "workflow_state",
)


def contract_digest(contract: dict[str, Any]) -> str:
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enterprise_ga_v3_0_contract() -> dict[str, Any]:
    document = load_openapi_contract()
    v2_0 = all_contracts()
    team_server = team_server_v2_1_contract()
    console = operator_console_v2_3_contract()
    contract = {
        "contract": "EnterpriseGA_V3_0",
        "contract_status": CONTRACT_STATUS,
        "ga_version": GA_VERSION,
        "api_path_prefix": API_PATH_PREFIX,
        "migration_from": MIGRATION_FROM,
        "decision_refs": list(DECISION_REFS),
        "openapi_x_contract_status": document.get("info", {}).get("x-contract-status"),
        "openapi_info_version": document.get("info", {}).get("version"),
        "supported_surfaces": list(SUPPORTED_SURFACES),
        "v2_0_rc_contracts": sorted(v2_0.keys()),
        "v2_0_rc_contract_digests": {
            name: contract_digest(payload) for name, payload in sorted(v2_0.items())
        },
        "team_server_contract": team_server["contract"],
        "team_server_digest": contract_digest(team_server),
        "operator_console_contract": console["contract"],
        "operator_console_digest": contract_digest(console),
        "console_routes": console["console_routes"],
        "service_plane_paths": team_server["service_plane_paths"],
        "cli_server_controls": team_server["cli_server_controls"],
    }
    scrubbed = _scrub_ga(contract)
    assert_snapshot_safe(scrubbed)
    return scrubbed


def _scrub_ga(value: Any) -> Any:
    if isinstance(value, str):
        from safecode.enterprise.contracts.v2_1 import _scrub_string

        return _scrub_string(value)
    if isinstance(value, list):
        return [_scrub_ga(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _scrub_ga(item) for key, item in value.items()}
    return value
