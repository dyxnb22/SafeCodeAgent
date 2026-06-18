"""ToolRegistry round-trip tests (v1.3.1-T1)."""

import json

import pytest

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.tools.registry import (
    ApprovalTier,
    ToolCategory,
    ToolNotRegisteredError,
    ToolRegistry,
    ToolRegistryConflictError,
    ToolSpec,
)


def _sample_spec(name: str = "read_file") -> ToolSpec:
    return ToolSpec(
        name=name,
        description="Read a local file",
        category=ToolCategory.read_local,
        approval_tier=ApprovalTier.AUTO,
        action=Action.retrieval_source_access,
        requires_network=False,
        requires_write=False,
        capabilities=["read"],
        audit_event="tool.executed",
    )


def test_tool_spec_json_round_trip():
    spec = _sample_spec()
    restored = ToolSpec.model_validate(json.loads(spec.model_dump_json()))
    assert restored == spec


def test_unknown_tool_lookup_returns_none():
    registry = ToolRegistry()
    assert registry.lookup("missing") is None


def test_require_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotRegisteredError):
        registry.require("missing")


def test_duplicate_registration_raises():
    registry = ToolRegistry()
    registry.register(_sample_spec())
    with pytest.raises(ToolRegistryConflictError):
        registry.register(_sample_spec())


def test_list_specs_sorted_by_name():
    registry = ToolRegistry()
    registry.register(_sample_spec("search"))
    registry.register(_sample_spec("read_file"))
    names = [item.name for item in registry.list_specs()]
    assert names == ["read_file", "search"]
