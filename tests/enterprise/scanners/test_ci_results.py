"""CI callback result schema tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from safecode.enterprise.scanners.results import (
    CI_CALLBACK_SCHEMA_VERSION,
    CiCallbackRequest,
    CiCallbackSchemaError,
    parse_ci_callback_request,
)


def test_callback_run_id_path_traversal_rejected_at_model_validation() -> None:
    with pytest.raises(ValidationError):
        CiCallbackRequest.model_validate(
            {
                "schema_version": CI_CALLBACK_SCHEMA_VERSION,
                "delivery_id": "ci-delivery-00123456",
                "run_id": "../../../etc",
                "outcome": "passed",
            }
        )


def test_callback_run_id_path_traversal_rejected_when_parsing_body() -> None:
    body = json.dumps(
        {
            "schema_version": CI_CALLBACK_SCHEMA_VERSION,
            "delivery_id": "ci-delivery-00123456",
            "run_id": "../../../etc",
            "outcome": "passed",
        }
    ).encode("utf-8")
    with pytest.raises(CiCallbackSchemaError):
        parse_ci_callback_request(body)
