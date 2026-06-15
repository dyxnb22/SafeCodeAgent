"""Tests for v5.3.1 context compaction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ContextCompactor.should_compact
# ---------------------------------------------------------------------------

class TestShouldCompact:
    def test_below_threshold_returns_false(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        compactor = ContextCompactor(MagicMock(), tmp_path, "s1", max_context_tokens=1000)
        assert compactor.should_compact(500) is False  # 500 < 600 (60%)

    def test_at_threshold_returns_true(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        compactor = ContextCompactor(MagicMock(), tmp_path, "s1", max_context_tokens=1000)
        assert compactor.should_compact(600) is True  # 600 >= 600

    def test_above_threshold_returns_true(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        compactor = ContextCompactor(MagicMock(), tmp_path, "s1", max_context_tokens=1000)
        assert compactor.should_compact(800) is True

    def test_custom_threshold_ratio(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        compactor = ContextCompactor(MagicMock(), tmp_path, "s1",
                                     threshold_ratio=0.80, max_context_tokens=1000)
        assert compactor.should_compact(799) is False
        assert compactor.should_compact(800) is True


# ---------------------------------------------------------------------------
# ContextCompactor.compact
# ---------------------------------------------------------------------------

class TestCompact:
    def _make_compactor(self, tmp_path, summary_response="Summary of results."):
        from safecode.context.compaction import ContextCompactor

        mock_llm = MagicMock()
        mock_llm.ask.return_value = MagicMock(content=summary_response)

        with patch("safecode.config.SafeCodeConfig.load") as mock_load:
            mock_cfg = MagicMock()
            mock_load.return_value = mock_cfg
            compactor = ContextCompactor(mock_llm, tmp_path, "sess-001")

        # Patch audit logger to avoid file I/O in tests
        with patch("safecode.context.compaction.ContextCompactor._audit_compact"):
            pass

        return compactor, mock_llm

    def test_compact_returns_summary(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        mock_llm = MagicMock()
        mock_llm.ask.return_value = MagicMock(content="Compact summary.")

        with patch("safecode.context.compaction.ContextCompactor._audit_compact"):
            with patch("safecode.config.SafeCodeConfig.load"):
                compactor = ContextCompactor(mock_llm, tmp_path, "sess-001")
                result = compactor.compact(["obs1", "obs2", "obs3"])

        assert "summary" in result.summary.lower() or result.summary == "Compact summary."
        assert result.observations_archived == 3

    def test_compact_archives_to_file(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        mock_llm = MagicMock()
        mock_llm.ask.return_value = MagicMock(content="Summary.")

        with patch("safecode.context.compaction.ContextCompactor._audit_compact"):
            with patch("safecode.config.SafeCodeConfig.load"):
                compactor = ContextCompactor(mock_llm, tmp_path, "sess-archive-test")
                compactor.compact(["line1", "line2"])

        archive = tmp_path / ".sac" / "sessions" / "sess-archive-test" / "observations_compacted_1.jsonl"
        assert archive.exists()
        lines = archive.read_text().splitlines()
        assert len(lines) == 2

    def test_two_compactions_produce_two_archives(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        mock_llm = MagicMock()
        mock_llm.ask.return_value = MagicMock(content="Summary.")

        with patch("safecode.context.compaction.ContextCompactor._audit_compact"):
            with patch("safecode.config.SafeCodeConfig.load"):
                compactor = ContextCompactor(mock_llm, tmp_path, "sess-two")
                compactor.compact(["obs-a1"])
                compactor.compact(["obs-b1", "obs-b2"])

        base = tmp_path / ".sac" / "sessions" / "sess-two"
        assert (base / "observations_compacted_1.jsonl").exists()
        assert (base / "observations_compacted_2.jsonl").exists()

    def test_compact_raises_on_llm_failure(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        mock_llm = MagicMock()
        mock_llm.ask.side_effect = RuntimeError("LLM down")

        with patch("safecode.config.SafeCodeConfig.load"):
            compactor = ContextCompactor(mock_llm, tmp_path, "sess-fail")

        with pytest.raises(RuntimeError, match="Compaction LLM call failed"):
            compactor.compact(["obs"])

    def test_compact_tokens_before_after(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        mock_llm = MagicMock()
        long_obs = "x" * 4000  # ~1000 tokens
        short_summary = "y" * 800  # ~200 tokens
        mock_llm.ask.return_value = MagicMock(content=short_summary)

        with patch("safecode.context.compaction.ContextCompactor._audit_compact"):
            with patch("safecode.config.SafeCodeConfig.load"):
                compactor = ContextCompactor(mock_llm, tmp_path, "sess-tokens")
                result = compactor.compact([long_obs])

        assert result.tokens_before > result.tokens_after


# ---------------------------------------------------------------------------
# Fresh session doesn't trigger compaction
# ---------------------------------------------------------------------------

class TestNoCompactionOnFreshSession:
    def test_fresh_session_below_threshold(self, tmp_path):
        from safecode.context.compaction import ContextCompactor
        mock_llm = MagicMock()
        compactor = ContextCompactor(mock_llm, tmp_path, "s-fresh", max_context_tokens=40000)
        # 1 small observation — should not trigger
        assert compactor.should_compact(100) is False


# ---------------------------------------------------------------------------
# AgentLoop._maybe_compact_context (v5.3.1)
# ---------------------------------------------------------------------------

class TestAgentLoopCompaction:
    def test_no_compaction_when_no_observations(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop(tmp_path)
        result = loop._maybe_compact_context("sess-empty")
        assert result is None

    def test_no_compaction_when_below_threshold(self, tmp_path):
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop(tmp_path)
        loop._session_observations = ["small observation"]
        # Default max_context_chars is very large; should not trigger
        result = loop._maybe_compact_context("sess-small")
        assert result is None

    def test_compaction_fires_when_over_threshold(self, tmp_path):
        """When observations exceed 60% of budget, compaction fires."""
        from safecode.agent.loop import AgentLoop
        from safecode.context.compaction import ContextCompactor

        mock_llm = MagicMock()
        mock_llm.ask.return_value = MagicMock(content="Compact result.")

        loop = AgentLoop(tmp_path, llm_client=mock_llm)
        # Override compactor with very small budget so threshold is easy to hit
        with patch("safecode.config.SafeCodeConfig.load"):
            compactor = ContextCompactor(mock_llm, tmp_path, "sess-over",
                                         max_context_tokens=10)  # tiny budget
        loop._compactor = compactor
        loop._session_observations = ["x" * 100]  # ~25 tokens > 6 (60% of 10)

        with patch("safecode.context.compaction.ContextCompactor._audit_compact"):
            result = loop._maybe_compact_context("sess-over")

        assert result is not None
        assert "Compact result." in result
        # Observations should be cleared after compaction
        assert loop._session_observations == []

    def test_observations_accumulated_from_native_turn(self, tmp_path):
        """native_step() should accumulate observations into _session_observations."""
        from safecode.agent.loop import AgentLoop
        from safecode.agent.schemas import AgentStopForUserResponse

        mock_llm = MagicMock()
        mock_llm.plan.return_value = MagicMock(steps=["read a file"])
        # First call: return a stop_for_user
        mock_llm.choose_tool_native.return_value = AgentStopForUserResponse(
            reason="done", message="done", requires_approval=False
        )

        loop = AgentLoop(tmp_path, llm_client=mock_llm)
        # The choose_tool_native returns stop so no dispatch; observations stay empty
        loop.native_step("test goal")
        # No tool calls were dispatched, so observations = []
        assert loop._session_observations == []
