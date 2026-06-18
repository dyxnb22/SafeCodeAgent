"""Native tool spec presence tests (v1.3.1-T2)."""

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.tools.native_specs import NATIVE_TOOL_NAMES, register_native_tools
from safecode.enterprise.tools.registry import ApprovalTier


def test_all_six_native_tools_present():
    registry = register_native_tools()
    for name in NATIVE_TOOL_NAMES:
        spec = registry.require(name)
        assert spec.name == name


def test_native_tool_approval_tiers_match_action_matrix():
    registry = register_native_tools()
    expected = {
        "read_file": (ApprovalTier.AUTO, Action.retrieval_source_access),
        "search": (ApprovalTier.AUTO, Action.retrieval_source_access),
        "command": (ApprovalTier.CONFIRM, Action.command_execute),
        "github_read": (ApprovalTier.AUTO, Action.github_read),
        "github_write": (ApprovalTier.GATE, Action.github_write_comment),
        "web_fetch": (ApprovalTier.CONFIRM, Action.mcp_read),
    }
    for name, (tier, action) in expected.items():
        spec = registry.require(name)
        assert spec.approval_tier == tier
        assert spec.action == action
