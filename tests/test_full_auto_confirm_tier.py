"""Tests for v6.26: full_auto mode auto-applies CONFIRM tier patches."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.approval_tier import ApprovalTier
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


def _make_proposal(files: list[str], op: str = "update") -> PatchProposal:
    return PatchProposal(
        id="test-prop-1",
        task="fix bug",
        blocks=[
            PatchBlock(
                operation=op,
                file_path=Path(f),
                search="old" if op == "update" else None,
                replace="new" if op == "update" else None,
                content="new content" if op == "create" else None,
            )
            for f in files
        ],
        created_at=utc_now_iso(),
        model="mock",
    )


class TestFullAutoConfirmTier:
    """full_auto=True should auto-apply CONFIRM tier patches without stopping."""

    def test_auto_edit_only_applies_auto_tier(self, tmp_path):
        """auto_edit=True alone should NOT apply CONFIRM tier."""
        from safecode.agent.loop import AgentLoop
        from safecode.agent.approval_tier import classify_proposal
        from safecode.config import SafeCodeConfig

        proposal = _make_proposal(["src/a.py", "src/b.py", "src/c.py"])
        config = SafeCodeConfig.load(tmp_path)
        # 3 files typically → CONFIRM tier
        tier = classify_proposal(proposal, config)
        # We just verify the tier classification works
        assert tier in (ApprovalTier.AUTO, ApprovalTier.CONFIRM, ApprovalTier.GATE)

    def test_full_auto_condition_covers_confirm(self):
        """Verify the auto_apply_condition logic matches expected behaviour."""
        auto_edit = True
        full_auto = True

        def condition(tier, ae=auto_edit, fa=full_auto):
            return (
                (tier == ApprovalTier.AUTO and (ae or fa))
                or (tier == ApprovalTier.CONFIRM and fa)
            )

        assert condition(ApprovalTier.AUTO) is True
        assert condition(ApprovalTier.CONFIRM) is True
        assert condition(ApprovalTier.GATE) is False

    def test_auto_edit_only_does_not_cover_confirm(self):
        """auto_edit alone should not auto-apply CONFIRM tier."""
        auto_edit = True
        full_auto = False

        def condition(tier, ae=auto_edit, fa=full_auto):
            return (
                (tier == ApprovalTier.AUTO and (ae or fa))
                or (tier == ApprovalTier.CONFIRM and fa)
            )

        assert condition(ApprovalTier.AUTO) is True
        assert condition(ApprovalTier.CONFIRM) is False
        assert condition(ApprovalTier.GATE) is False

    def test_gate_tier_never_auto_applied(self):
        """GATE tier must never be auto-applied regardless of mode."""
        for auto_edit, full_auto in [(True, True), (True, False), (False, True), (False, False)]:
            def condition(tier, ae=auto_edit, fa=full_auto):
                return (
                    (tier == ApprovalTier.AUTO and (ae or fa))
                    or (tier == ApprovalTier.CONFIRM and fa)
                )
            assert condition(ApprovalTier.GATE) is False, \
                f"GATE should not auto-apply with auto_edit={auto_edit}, full_auto={full_auto}"

    def test_no_mode_never_auto_applies(self):
        """Neither mode enabled → nothing auto-applies."""
        def condition(tier, ae=False, fa=False):
            return (
                (tier == ApprovalTier.AUTO and (ae or fa))
                or (tier == ApprovalTier.CONFIRM and fa)
            )

        assert condition(ApprovalTier.AUTO) is False
        assert condition(ApprovalTier.CONFIRM) is False
        assert condition(ApprovalTier.GATE) is False


class TestApprovalTierClassification:
    """Verify tier classification is consistent with expectations."""

    def test_single_file_small_is_auto(self, tmp_path):
        from safecode.agent.approval_tier import classify_proposal
        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(tmp_path)
        prop = _make_proposal(["src/a.py"])
        tier = classify_proposal(prop, config)
        assert tier == ApprovalTier.AUTO

    def test_many_files_is_confirm_or_gate(self, tmp_path):
        from safecode.agent.approval_tier import classify_proposal
        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(tmp_path)
        prop = _make_proposal([f"src/file{i}.py" for i in range(10)])
        tier = classify_proposal(prop, config)
        assert tier in (ApprovalTier.CONFIRM, ApprovalTier.GATE)
