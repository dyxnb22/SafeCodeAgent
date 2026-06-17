"""Tests for tiered approval classifier (v6.8.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.agent.approval_tier import ApprovalTier, classify_proposal, tier_label
from safecode.config import ApprovalConfig
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


def _proposal(blocks: list[dict]) -> PatchProposal:
    patch_blocks = []
    for b in blocks:
        patch_blocks.append(PatchBlock(
            operation=b.get("operation", "update"),
            file_path=Path(b.get("file_path", "src/foo.py")),
            search=b.get("search"),
            replace=b.get("replace"),
            content=b.get("content"),
        ))
    return PatchProposal(
        id="test-id",
        task="test task",
        blocks=patch_blocks,
        created_at=utc_now_iso(),
        model="mock",
    )


class TestApprovalTierGate:
    def test_delete_block_is_gate(self) -> None:
        p = _proposal([{"operation": "delete", "file_path": "src/foo.py"}])
        assert classify_proposal(p) == ApprovalTier.GATE

    def test_create_block_is_gate(self) -> None:
        p = _proposal([{"operation": "create", "file_path": "src/new.py", "content": "x = 1"}])
        assert classify_proposal(p) == ApprovalTier.GATE

    def test_mixed_update_delete_is_gate(self) -> None:
        p = _proposal([
            {"operation": "update", "file_path": "src/foo.py", "search": "old", "replace": "new"},
            {"operation": "delete", "file_path": "src/bar.py"},
        ])
        assert classify_proposal(p) == ApprovalTier.GATE


class TestApprovalTierConfirm:
    def test_multi_file_update_is_confirm(self) -> None:
        p = _proposal([
            {"operation": "update", "file_path": "src/foo.py", "search": "a", "replace": "b"},
            {"operation": "update", "file_path": "src/bar.py", "search": "c", "replace": "d"},
        ])
        assert classify_proposal(p) == ApprovalTier.CONFIRM

    def test_single_file_logic_change_is_confirm(self) -> None:
        replace = "def new_func():\n    return 42\n"
        p = _proposal([{"operation": "update", "file_path": "src/foo.py",
                        "search": "old", "replace": replace}])
        assert classify_proposal(p) == ApprovalTier.CONFIRM

    def test_class_definition_is_confirm(self) -> None:
        replace = "class NewClass:\n    pass\n"
        p = _proposal([{"operation": "update", "file_path": "src/foo.py",
                        "search": "old", "replace": replace}])
        assert classify_proposal(p) == ApprovalTier.CONFIRM

    def test_import_statement_is_confirm(self) -> None:
        replace = "import json\nfrom pathlib import Path\n"
        p = _proposal([{"operation": "update", "file_path": "src/foo.py",
                        "search": "old", "replace": replace}])
        assert classify_proposal(p) == ApprovalTier.CONFIRM

    def test_binary_file_extension_is_confirm(self) -> None:
        p = _proposal([{"operation": "update", "file_path": "src/foo.lock",
                        "search": "old", "replace": "new"}])
        assert classify_proposal(p) == ApprovalTier.CONFIRM


class TestApprovalTierAuto:
    def test_markdown_file_is_auto(self) -> None:
        p = _proposal([{"operation": "update", "file_path": "README.md",
                        "search": "old text", "replace": "new text"}])
        assert classify_proposal(p) == ApprovalTier.AUTO

    def test_toml_config_default_is_confirm(self) -> None:
        p = _proposal([{"operation": "update", "file_path": "pyproject.toml",
                        "search": "old", "replace": "new"}])
        assert classify_proposal(p) == ApprovalTier.CONFIRM

    def test_yaml_file_is_auto(self) -> None:
        p = _proposal([{"operation": "update", "file_path": ".github/workflows/ci.yml",
                        "search": "old", "replace": "new"}])
        assert classify_proposal(p) == ApprovalTier.AUTO

    def test_comment_only_python_is_auto(self) -> None:
        replace = "# Updated comment explaining the function\n# More detail here\n"
        p = _proposal([{"operation": "update", "file_path": "src/foo.py",
                        "search": "# old comment", "replace": replace}])
        assert classify_proposal(p) == ApprovalTier.AUTO

    def test_docstring_addition_is_auto(self) -> None:
        replace = '"""This function does X.\n\nReturns Y.\n"""\n'
        p = _proposal([{"operation": "update", "file_path": "src/foo.py",
                        "search": "old", "replace": replace}])
        assert classify_proposal(p) == ApprovalTier.AUTO

    def test_txt_file_is_auto(self) -> None:
        p = _proposal([{"operation": "update", "file_path": "docs/notes.txt",
                        "search": "old", "replace": "new"}])
        assert classify_proposal(p) == ApprovalTier.AUTO

    def test_threshold_can_make_large_docs_confirm(self) -> None:
        p = _proposal([{"operation": "update", "file_path": "README.md",
                        "search": "old", "replace": "\n".join(f"line {i}" for i in range(20))}])
        cfg = ApprovalConfig(auto_max_changed_lines=3)
        assert classify_proposal(p, cfg) == ApprovalTier.CONFIRM

    def test_never_auto_path_can_be_configured(self) -> None:
        p = _proposal([{"operation": "update", "file_path": "docs/notes.txt",
                        "search": "old", "replace": "new"}])
        cfg = ApprovalConfig(never_auto_paths=["docs/"])
        assert classify_proposal(p, cfg) == ApprovalTier.CONFIRM


class TestTierLabel:
    def test_all_tiers_have_labels(self) -> None:
        for tier in ApprovalTier:
            label = tier_label(tier)
            assert isinstance(label, str)
            assert len(label) > 3

    def test_auto_label_contains_no_pause(self) -> None:
        assert "no pause" in tier_label(ApprovalTier.AUTO)

    def test_gate_label_contains_explicit(self) -> None:
        assert "explicit" in tier_label(ApprovalTier.GATE)


class TestApprovalConfigMerge:
    def test_project_config_cannot_relax_user_approval_limits(self) -> None:
        from safecode.config import SafeCodeConfig, merge_trusted_config

        user = SafeCodeConfig()
        user.approval.mode = "suggest"
        user.approval.auto_max_files = 1
        user.approval.auto_max_changed_lines = 5
        user.approval.never_auto_paths = ["secrets/"]

        project = SafeCodeConfig()
        project.approval.mode = "full-auto"
        project.approval.auto_max_files = 9
        project.approval.auto_max_changed_lines = 99
        project.approval.never_auto_paths = ["generated/"]

        merged = merge_trusted_config(user, project)

        assert merged.approval.mode == "suggest"
        assert merged.approval.auto_max_files == 1
        assert merged.approval.auto_max_changed_lines == 5
        assert "secrets/" in merged.approval.never_auto_paths
        assert "generated/" in merged.approval.never_auto_paths


class TestAutoApplyInLoop:
    """Verify the AUTO tier triggers auto-apply in auto_edit mode."""

    def test_auto_tier_does_not_stop_for_approval_in_auto_edit(self, tmp_path: Path) -> None:
        """When auto_edit=True and tier=AUTO, patch is applied without stopping."""
        from unittest.mock import patch, MagicMock
        from safecode.agent.loop import AgentLoop
        from safecode.agent.session import AgentSessionState
        from safecode.agent.schemas import AgentStopForUserResponse

        # Minimal session state
        state = AgentSessionState(
            session_id="test-session-auto-tier-001",
            goal="add a comment",
            plan=["add comment"],
            current_step=0,
            status="active",
            pending_action=None,
            last_observation="",
            last_error=None,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

        mock_proposal = PatchProposal(
            id="pid1",
            task="add comment",
            blocks=[PatchBlock(
                operation="update",
                file_path=Path("README.md"),
                search="old",
                replace="# new comment\n",
            )],
            created_at="2026-01-01T00:00:00+00:00",
            model="mock",
        )

        mock_edit_result = MagicMock()
        mock_edit_result.proposal = mock_proposal
        mock_edit_result.pending_patch_path = tmp_path / ".sac" / "pending_patch.json"
        mock_edit_result.scope_result = None

        mock_apply_result = MagicMock()
        mock_apply_result.checkpoint.checkpoint_id = "cp-001"

        with patch("safecode.agent.loop.AgentOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.edit.return_value = mock_edit_result
            instance.apply.return_value = mock_apply_result

            loop = AgentLoop(tmp_path, auto_edit=True, no_clarify=True)
            loop.store.save(state)

            from safecode.agent.tools import RoutedToolIntent, ToolIntent
            routed = RoutedToolIntent(
                intent=ToolIntent(
                    type="patch",
                    target="add comment",
                    description="add comment",
                    tool_name="patch.propose",
                ),
                route="patch.propose",
                requires_approval=True,
                executable_now=False,
                reason="patch",
            )

            result = loop._execute_patch_proposal_step("add comment", state, routed)

        # AUTO tier + auto_edit → should NOT stop for approval
        assert not result.stopped_for_approval
        assert "auto-applied" in (result.observation or "").lower()
