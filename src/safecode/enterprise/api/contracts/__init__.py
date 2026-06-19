"""Planned Team Server API contracts (v2.1)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONTRACT_STATUS = "planned"
OPENAPI_RELATIVE_PATH = Path("contracts") / "openapi.yaml"
OPENAPI_PATH = Path(__file__).resolve().parent / "openapi.yaml"

# Normative Service Plane paths from platform-architecture-v2.md.
SERVICE_PLANE_PATHS: tuple[str, ...] = (
    "/healthz",
    "/readyz",
    "/version",
    "/v2/runs",
    "/v2/runs/{run_id}",
    "/v2/runs/{run_id}/resume",
    "/v2/runs/{run_id}/cancel",
    "/v2/runs/{run_id}/timeline",
    "/v2/runs/{run_id}/trace",
    "/v2/approvals",
    "/v2/approvals/{approval_id}/decide",
    "/v2/approvals/{approval_id}/revoke",
    "/v2/evidence/{run_id}",
    "/v2/eval/baselines",
    "/v2/webhooks/github",
    "/v2/ci/callback",
)

BUSINESS_PATH_PREFIXES: tuple[str, ...] = ("/v2/",)


@lru_cache(maxsize=1)
def load_openapi_contract() -> dict[str, Any]:
    """Load the planned OpenAPI document with safe YAML parsing."""
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def list_operation_ids(document: dict[str, Any] | None = None) -> list[str]:
    doc = document if document is not None else load_openapi_contract()
    operation_ids: list[str] = []
    for path_item in doc.get("paths", {}).values():
        for method, operation in path_item.items():
            if method.startswith("x-"):
                continue
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(str(operation_id))
    return operation_ids


def is_business_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in BUSINESS_PATH_PREFIXES)
