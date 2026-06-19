"""Planned OpenAPI contract tests (v2.1.1-T3)."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from safecode.enterprise.api.contracts import (
    BUSINESS_PATH_PREFIXES,
    CONTRACT_STATUS,
    OPENAPI_PATH,
    SERVICE_PLANE_PATHS,
    is_business_path,
    list_operation_ids,
    load_openapi_contract,
)

FORBIDDEN_PROPERTY_NAMES = {
    "secret",
    "password",
    "api_key",
    "private_key",
    "token",
    "debug",
    "debug_payload",
    "raw_prompt",
}


def _iter_schema_properties(schema: dict[str, Any]) -> list[str]:
    names: list[str] = []
    if not isinstance(schema, dict):
        return names
    properties = schema.get("properties")
    if isinstance(properties, dict):
        names.extend(str(name) for name in properties)
    for key in ("allOf", "oneOf", "anyOf"):
        for item in schema.get(key, []):
            names.extend(_iter_schema_properties(item))
    items = schema.get("items")
    if isinstance(items, dict):
        names.extend(_iter_schema_properties(items))
    return names


def _collect_component_property_names(document: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    schemas = document.get("components", {}).get("schemas", {})
    for schema in schemas.values():
        names.update(_iter_schema_properties(schema))
    return names


def test_openapi_contract_safe_loads() -> None:
    raw = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert raw["openapi"].startswith("3.")
    assert load_openapi_contract() == raw


def test_operation_ids_are_unique() -> None:
    operation_ids = list_operation_ids()
    assert operation_ids
    assert len(operation_ids) == len(set(operation_ids))


@pytest.mark.parametrize("path", SERVICE_PLANE_PATHS)
def test_service_plane_paths_are_present(path: str) -> None:
    document = load_openapi_contract()
    assert path in document["paths"]


def test_contract_status_is_planned_not_delivered() -> None:
    document = load_openapi_contract()
    assert document["info"]["x-contract-status"] == CONTRACT_STATUS == "planned"
    serialized = json.dumps(document)
    assert "delivered" not in serialized.lower()


def test_run_status_includes_cancelled_distinct_from_rejected_and_blocked() -> None:
    document = load_openapi_contract()
    statuses = document["components"]["schemas"]["RunStatus"]["enum"]
    assert "cancelled" in statuses
    assert "rejected" in statuses
    assert "blocked" in statuses
    assert statuses.index("cancelled") != statuses.index("rejected")
    assert statuses.index("cancelled") != statuses.index("blocked")


def test_business_endpoints_require_bearer_auth() -> None:
    document = load_openapi_contract()
    for path, path_item in document["paths"].items():
        if not is_business_path(path):
            continue
        for method, operation in path_item.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            security = operation.get("security")
            assert security == [{"bearerAuth": []}], f"{method.upper()} {path} missing bearer auth"


def test_probe_endpoints_have_no_security_requirement() -> None:
    document = load_openapi_contract()
    for path in ("/healthz", "/readyz", "/version"):
        for operation in document["paths"][path].values():
            if not isinstance(operation, dict):
                continue
            assert "security" not in operation


def test_no_debug_or_secret_response_fields() -> None:
    document = load_openapi_contract()
    property_names = _collect_component_property_names(document)
    violations = sorted(name for name in property_names if name in FORBIDDEN_PROPERTY_NAMES)
    assert not violations, f"forbidden response fields present: {violations}"


def test_problem_details_schema_is_typed_and_bounded() -> None:
    document = load_openapi_contract()
    problem = document["components"]["schemas"]["ProblemDetails"]
    assert problem["additionalProperties"] is False
    assert "detail" in problem["properties"]
    assert problem["properties"]["detail"]["maxLength"] == 512


def _resolve_parameter_names(document: dict[str, Any], parameters: list[Any]) -> set[str]:
    names: set[str] = set()
    components = document.get("components", {}).get("parameters", {})
    for parameter in parameters:
        if isinstance(parameter, dict) and "$ref" in parameter:
            ref = parameter["$ref"].split("/")[-1]
            resolved = components.get(ref, {})
            if resolved.get("name"):
                names.add(str(resolved["name"]))
        elif isinstance(parameter, dict) and parameter.get("name"):
            names.add(str(parameter["name"]))
    return names


def test_command_endpoints_declare_idempotency_key() -> None:
    document = load_openapi_contract()
    command_paths = [
        "/v2/runs",
        "/v2/runs/{run_id}/resume",
        "/v2/runs/{run_id}/cancel",
        "/v2/approvals/{approval_id}/decide",
        "/v2/approvals/{approval_id}/revoke",
        "/v2/webhooks/github",
        "/v2/ci/callback",
    ]
    for path in command_paths:
        post = document["paths"][path]["post"]
        header_names = {
            name
            for name in _resolve_parameter_names(document, post.get("parameters", []))
        }
        assert "Idempotency-Key" in header_names, path
