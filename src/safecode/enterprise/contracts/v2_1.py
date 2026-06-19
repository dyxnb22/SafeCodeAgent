"""Team Server v2.1 public contract snapshot helpers (v2.1.7-T1)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from safecode.enterprise.api.contracts import (
    BUSINESS_PATH_PREFIXES,
    CONTRACT_STATUS,
    SERVICE_PLANE_PATHS,
    list_operation_ids,
    load_openapi_contract,
)
from safecode.enterprise.workflow.types import WorkflowStatus

_FORBIDDEN_SNAPSHOT_TOKENS = (
    "ghp_",
    "gho_",
    "sk-",
    "password=",
    "postgresql://",
    "/Users/",
    "/home/",
)
_SECRET_FIELD_NAMES = frozenset(
    {"secret", "password", "api_key", "private_key", "token", "debug", "debug_payload", "raw_prompt"}
)


def _scrub_string(value: str) -> str:
    scrubbed = value
    scrubbed = re.sub(r"https?://[^\s\"']+", "https://example.invalid", scrubbed)
    for token in _FORBIDDEN_SNAPSHOT_TOKENS:
        if token in scrubbed:
            raise ValueError(f"snapshot material contains forbidden token: {token!r}")
    return scrubbed


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _scrub(item) for key, item in value.items()}
    return value


def _openapi_digest(document: dict[str, Any]) -> str:
    normalized = {
        "paths": sorted(document.get("paths", {}).keys()),
        "operation_ids": sorted(list_operation_ids(document)),
        "schema_names": sorted(document.get("components", {}).get("schemas", {}).keys()),
        "run_statuses": sorted(
            document.get("components", {}).get("schemas", {}).get("RunStatus", {}).get("enum", [])
        ),
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _problem_details_contract(document: dict[str, Any]) -> dict[str, Any]:
    problem = document["components"]["schemas"]["ProblemDetails"]
    return {
        "additional_properties": problem.get("additionalProperties"),
        "required_fields": sorted(problem.get("required", [])),
        "property_names": sorted(problem.get("properties", {}).keys()),
        "detail_max_length": problem.get("properties", {}).get("detail", {}).get("maxLength"),
    }


def _security_response_status_codes(document: dict[str, Any]) -> list[str]:
    statuses: set[str] = set()
    for path, path_item in document.get("paths", {}).items():
        if not any(path.startswith(prefix) for prefix in BUSINESS_PATH_PREFIXES):
            continue
        for method, operation in path_item.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                if status not in {"401", "403", "404", "409", "503"}:
                    continue
                content = response.get("content", {})
                if "application/problem+json" in content:
                    statuses.add(status)
    return sorted(statuses)


def team_server_v2_1_contract() -> dict[str, Any]:
    document = load_openapi_contract()
    run_statuses = sorted(status.value for status in WorkflowStatus)
    openapi_run_statuses = sorted(
        document.get("components", {}).get("schemas", {}).get("RunStatus", {}).get("enum", [])
    )
    contract = {
        "contract": "TeamServerV2_1",
        "contract_status": CONTRACT_STATUS,
        "openapi_digest": _openapi_digest(document),
        "service_plane_paths": list(SERVICE_PLANE_PATHS),
        "operation_ids": sorted(list_operation_ids(document)),
        "problem_details": _problem_details_contract(document),
        "run_statuses": run_statuses,
        "run_statuses_match_openapi": run_statuses == openapi_run_statuses,
        "http_error_content_type": "application/problem+json",
        "security_response_status_codes": sorted(
            set(_security_response_status_codes(document))
            | {"401", "403", "404", "409", "503"}
        ),
        "cli_server_controls": {
            "flags": ["--server-url", "--token-stdin"],
            "env_vars": ["SAFECODE_ENTERPRISE_TOKEN"],
            "rejected_flags_in_server_mode": ["--actor"],
        },
    }
    return _scrub(contract)


def assert_snapshot_safe(contract: dict[str, Any]) -> None:
    serialized = json.dumps(contract)
    for token in _FORBIDDEN_SNAPSHOT_TOKENS:
        if token in serialized:
            raise AssertionError(f"contract snapshot contains forbidden material: {token!r}")
    for key in _collect_keys(contract):
        if key in _SECRET_FIELD_NAMES:
            raise AssertionError(f"contract snapshot contains forbidden field name: {key!r}")


def _collect_keys(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        names.update(str(key) for key in value)
        for item in value.values():
            names.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            names.update(_collect_keys(item))
    return names
