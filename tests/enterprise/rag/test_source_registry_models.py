"""Tests for KnowledgeSource and SourceType models (v1.1.1-T1)."""

import json

from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType


def test_source_type_enum_values():
    assert SourceType.security_policy.value == "security_policy"
    assert SourceType.runbook.value == "runbook"
    assert len(SourceType) >= 7


def test_knowledge_source_fields_and_defaults():
    source = KnowledgeSource(
        source_id="policy-secure-sql-001",
        source_type=SourceType.security_policy,
        name="Secure SQL",
        path_or_uri="examples/enterprise/policies/secure-sql.md",
        owner="appsec-team",
        permission_scope=["org", "appsec"],
        refresh_cadence="static",
        parser="markdown",
        metadata={"cwe": "CWE-89"},
    )
    assert source.tenant_id == "local"
    assert source.permission_scope == ["org", "appsec"]
    assert source.metadata["cwe"] == "CWE-89"


def test_knowledge_source_json_round_trip_preserves_field_order():
    source = KnowledgeSource(
        source_id="code-app",
        source_type=SourceType.code,
        tenant_id="local",
        name="Application code",
        path_or_uri="examples/enterprise/sample_app/",
        owner="developers",
        permission_scope=["org"],
        refresh_cadence="on_demand",
        parser="code",
        metadata={},
    )
    payload = source.model_dump(mode="json")
    encoded = json.dumps(payload, separators=(",", ":"))
    decoded = json.loads(encoded)
    restored = KnowledgeSource.model_validate(decoded)
    assert restored == source
    assert list(decoded.keys()) == list(payload.keys())


def test_empty_permission_scope_is_allowed():
    source = KnowledgeSource(
        source_id="restricted",
        source_type=SourceType.runbook,
        name="Restricted",
        path_or_uri="runbook.md",
        owner="secops",
        permission_scope=[],
        refresh_cadence="static",
        parser="markdown",
    )
    assert source.permission_scope == []
