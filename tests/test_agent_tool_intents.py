"""Tool intent router tests for v1.9.3."""

from __future__ import annotations

import pytest

from safecode.agent.tools import ToolIntentRouter


class TestToolIntentRouter:
    def test_read_intent_routes_without_approval(self):
        routed = ToolIntentRouter().route(
            {"type": "read", "target": "README.md", "description": "inspect docs"}
        )

        assert routed.route == "context.read"
        assert routed.executable_now is True
        assert routed.intent.requires_approval is False

    @pytest.mark.parametrize(
        ("intent_type", "payload", "route"),
        [
            ("patch", {"target": "src/app.py"}, "patch.propose"),
            ("shell", {"command": "pytest -q"}, "shell.propose"),
            ("sandbox", {"command": "pytest -q"}, "sandbox.propose"),
            ("mcp", {"tool_name": "notion.search"}, "mcp.propose"),
        ],
    )
    def test_write_or_execute_intents_require_approval(self, intent_type, payload, route):
        routed = ToolIntentRouter().route({"type": intent_type, **payload})

        assert routed.route == route
        assert routed.executable_now is False
        assert routed.intent.requires_approval is True
        assert routed.reason == "approval_required"

    def test_unknown_intent_fails_closed(self):
        with pytest.raises(ValueError, match="Invalid tool intent"):
            ToolIntentRouter().route({"type": "unknown", "target": "x"})

    def test_missing_required_field_fails_closed(self):
        with pytest.raises(ValueError, match="requires command"):
            ToolIntentRouter().route({"type": "shell"})
