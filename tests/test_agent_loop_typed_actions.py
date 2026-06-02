"""Tests for typed pending-action objects (v2.8.3).

Covers approval-required, patch-required, and stop-for-user actions.
Verifies that loop no longer uses boolean stringification for pending decisions.
"""

from __future__ import annotations

import pytest

from safecode.agent.pending_action import (
    PatchPendingAction,
    PendingAction,
    StopForUserAction,
    ToolPendingAction,
    pending_action_from_dict,
    render_pending_action,
)


class TestStopForUserAction:
    def test_type_is_stop_for_user(self):
        action = StopForUserAction(reason="x", message="y")
        assert action.type == "stop_for_user"

    def test_to_dict_has_proper_bool(self):
        action = StopForUserAction(reason="need input", message="msg", requires_approval=True)
        d = action.to_dict()
        assert d["requires_approval"] is True
        assert d["type"] == "stop_for_user"
        assert d["reason"] == "need input"
        assert d["message"] == "msg"

    def test_to_dict_false_approval(self):
        action = StopForUserAction(reason="r", message="m", requires_approval=False)
        d = action.to_dict()
        assert d["requires_approval"] is False

    def test_no_string_booleans(self):
        action = StopForUserAction(reason="r", message="m", requires_approval=True)
        d = action.to_dict()
        assert d["requires_approval"] not in ("true", "false", "True", "False")

    def test_render_with_message(self):
        action = StopForUserAction(reason="r", message="Need file name")
        label = render_pending_action(action)
        assert "Need file name" in label
        assert "approval required" in label.lower()

    def test_render_no_approval_no_tag(self):
        action = StopForUserAction(reason="r", message="m", requires_approval=False)
        label = render_pending_action(action)
        assert "approval" not in label.lower()


class TestPatchPendingAction:
    def test_type_is_patch(self):
        action = PatchPendingAction(reason="test")
        assert action.type == "patch"

    def test_to_dict_requires_approval_is_bool(self):
        action = PatchPendingAction(
            reason="patch_proposal_awaiting_approval",
            patch_id="abc123",
            requires_approval=True,
        )
        d = action.to_dict()
        assert d["requires_approval"] is True
        assert d["requires_approval"] not in ("true", "false")

    def test_to_dict_includes_files(self):
        action = PatchPendingAction(
            reason="r",
            patch_id="pid",
            files=("src/foo.py", "src/bar.py"),
        )
        d = action.to_dict()
        assert d["files"] == ["src/foo.py", "src/bar.py"]

    def test_to_dict_omits_empty_fields(self):
        action = PatchPendingAction(reason="pending_patch_already_exists")
        d = action.to_dict()
        assert "patch_id" not in d
        assert "files" not in d
        assert "pending_patch_path" not in d

    def test_pending_patch_already_exists_shape(self):
        action = PatchPendingAction(
            route="patch.propose",
            requires_approval=True,
            reason="pending_patch_already_exists",
            pending_patch_path="/proj/.sac/pending_patch.json",
        )
        d = action.to_dict()
        assert d["type"] == "patch"
        assert d["reason"] == "pending_patch_already_exists"
        assert d["requires_approval"] is True
        assert d["pending_patch_path"] == "/proj/.sac/pending_patch.json"

    def test_patch_proposal_awaiting_approval_shape(self):
        action = PatchPendingAction(
            route="patch.propose",
            requires_approval=True,
            reason="patch_proposal_awaiting_approval",
            patch_id="pid-001",
            pending_patch_path="/proj/.sac/pending_patch.json",
            files=("src/calc.py",),
        )
        d = action.to_dict()
        assert d["patch_id"] == "pid-001"
        assert d["files"] == ["src/calc.py"]

    def test_render_with_patch_id(self):
        action = PatchPendingAction(reason="patch_proposal_awaiting_approval", patch_id="pid001")
        label = render_pending_action(action)
        assert "pid001" in label
        assert "approval" in label.lower()

    def test_render_without_patch_id(self):
        action = PatchPendingAction(reason="pending_patch_already_exists")
        label = render_pending_action(action)
        assert "pending" in label.lower()


class TestToolPendingAction:
    def test_to_dict_executable_now_is_bool(self):
        action = ToolPendingAction(
            type="sandbox",
            route="sandbox.propose",
            executable_now=False,
            requires_approval=True,
            reason="needs approval",
        )
        d = action.to_dict()
        assert d["executable_now"] is False
        assert d["requires_approval"] is True
        assert d["executable_now"] not in ("true", "false")
        assert d["requires_approval"] not in ("true", "false")

    def test_intent_fields_merged_into_dict(self):
        action = ToolPendingAction(
            type="read",
            route="context.read",
            executable_now=True,
            requires_approval=False,
            reason="ok",
            intent_fields={"target": "src/foo.py", "description": "Read file"},
        )
        d = action.to_dict()
        assert d["target"] == "src/foo.py"
        assert d["description"] == "Read file"

    def test_type_not_overridden_by_intent_fields(self):
        action = ToolPendingAction(
            type="read",
            route="context.read",
            executable_now=True,
            requires_approval=False,
            reason="ok",
            intent_fields={"type": "should_be_overridden"},
        )
        d = action.to_dict()
        assert d["type"] == "read"

    def test_render_approval_required(self):
        action = ToolPendingAction(
            type="sandbox",
            route="sandbox.propose",
            requires_approval=True,
        )
        label = render_pending_action(action)
        assert "approval required" in label.lower()

    def test_render_not_executable(self):
        action = ToolPendingAction(
            type="mcp",
            route="mcp.propose",
            executable_now=False,
            requires_approval=False,
        )
        label = render_pending_action(action)
        assert "not executable" in label.lower()


class TestPendingActionFromDict:
    def test_stop_for_user_roundtrip(self):
        original = StopForUserAction(reason="r", message="m", requires_approval=True)
        restored = pending_action_from_dict(original.to_dict())
        assert isinstance(restored, StopForUserAction)
        assert restored.reason == "r"
        assert restored.message == "m"
        assert restored.requires_approval is True

    def test_patch_roundtrip(self):
        original = PatchPendingAction(
            route="patch.propose",
            requires_approval=True,
            reason="patch_proposal_awaiting_approval",
            patch_id="pid-001",
            files=("a.py", "b.py"),
        )
        restored = pending_action_from_dict(original.to_dict())
        assert isinstance(restored, PatchPendingAction)
        assert restored.patch_id == "pid-001"
        assert restored.files == ("a.py", "b.py")

    def test_unknown_type_returns_tool_action(self):
        d = {"type": "mcp", "route": "mcp.call_readonly", "executable_now": True}
        restored = pending_action_from_dict(d)
        assert isinstance(restored, ToolPendingAction)
        assert restored.type == "mcp"

    def test_empty_dict_returns_none(self):
        assert pending_action_from_dict({}) is None

    def test_no_type_returns_none(self):
        assert pending_action_from_dict({"route": "x"}) is None

    def test_bool_preserved_from_dict(self):
        # Ensure proper booleans survive round-trip (not string coercion)
        d = {"type": "stop_for_user", "reason": "r", "message": "m", "requires_approval": True}
        restored = pending_action_from_dict(d)
        assert isinstance(restored, StopForUserAction)
        assert restored.requires_approval is True


class TestLoopProducesTypedActions:
    """Verify the loop produces proper boolean types, not stringified ones."""

    def test_loop_stop_for_user_has_bool_requires_approval(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop(tmp_path)
        state = loop.store.start(
            "test goal",
            plan=[
                "Inspect current project state and user goal.",
                "Choose the next safe tool action.",
                "Stop before any write or command execution that needs approval.",
            ],
        )
        # Run one step and check the pending action shape
        result = loop.run("test goal", max_steps=5)
        action = result.state.pending_action
        if action is not None and "requires_approval" in action:
            assert isinstance(action["requires_approval"], bool), (
                f"requires_approval should be bool, got {type(action['requires_approval'])}: "
                f"{action['requires_approval']!r}"
            )

    def test_loop_patch_proposal_has_bool_requires_approval(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        src = tmp_path / "src"
        src.mkdir()
        (src / "calculator.py").write_text(
            "def add(a, b):\n    return a - b\n", encoding="utf-8"
        )
        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        action = result.state.pending_action
        if action is not None and action.get("type") == "patch":
            assert action.get("requires_approval") is True
            assert action.get("requires_approval") not in ("true", "false")
