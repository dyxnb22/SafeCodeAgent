"""Tests for T-3.4.2-A: Parent-side subagent finding synthesis."""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

from safecode.subagents.merge_policy import SubagentFinding
from safecode.subagents.synthesis import SubagentSynthesisResult, synthesize_findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finding(
    task_id: str = "abc",
    summary: str = "found something",
    observations: list[str] | None = None,
    files_inspected: list[str] | None = None,
    errors: list[str] | None = None,
    blocked: bool = False,
    success: bool = True,
) -> SubagentFinding:
    return SubagentFinding(
        task_id=task_id,
        summary=summary,
        observations=observations or [],
        files_inspected=files_inspected or [],
        errors=errors or [],
        blocked=blocked,
        success=success,
    )


def _mock_llm_client(content: str = "Synthesized result.\n- key point 1\n- key point 2") -> MagicMock:
    client = MagicMock()
    answer = MagicMock()
    answer.content = content
    client.ask.return_value = answer
    return client


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class TestSubagentSynthesisResult:
    def test_is_frozen(self):
        r = SubagentSynthesisResult(summary="x")
        with pytest.raises((AttributeError, TypeError)):
            r.summary = "y"  # type: ignore[misc]

    def test_defaults(self):
        r = SubagentSynthesisResult(summary="hello")
        assert r.summary == "hello"
        assert r.key_findings == []
        assert r.risks == []
        assert r.source_task_ids == []
        assert r.used_fallback is False


# ---------------------------------------------------------------------------
# Synthesis: parent calls before consuming merged findings
# ---------------------------------------------------------------------------


class TestSynthesisCalledBeforeConsumption:
    def test_synthesis_returns_result(self):
        findings = [_finding("t1"), _finding("t2")]
        result = synthesize_findings(findings)
        assert isinstance(result, SubagentSynthesisResult)

    def test_original_findings_list_unchanged(self):
        """synthesize_findings must not mutate the input list."""
        findings = [_finding("t1", "summary A"), _finding("t2", "summary B")]
        original_ids = [f.task_id for f in findings]
        original_summaries = [f.summary for f in findings]
        synthesize_findings(findings)
        assert [f.task_id for f in findings] == original_ids
        assert [f.summary for f in findings] == original_summaries

    def test_synthesis_called_from_loop_enrichment(self, tmp_path):
        """_enrich_with_subagent_findings calls synthesis before consuming merged list."""
        from unittest.mock import patch
        from safecode.agent.loop import AgentLoop
        from safecode.config import SafeCodeConfig

        with patch("safecode.agent.loop.SafeCodeConfig") as mock_cfg_cls:
            mock_cfg_cls.load.return_value = SafeCodeConfig()
            loop = AgentLoop(project_root=tmp_path)

        merged_mock = MagicMock()
        merged_mock.source_task_ids = ["t1"]
        merged_mock.blocked_task_ids = []
        merged_mock.errors = []
        merged_mock.summary = "clean summary"
        merged_mock.observations = []
        merged_mock.files_inspected = []

        finding = _finding("t1", "clean summary")

        synthesis_called_before = []

        def fake_synthesize(findings_arg, client, **kwargs):
            synthesis_called_before.append(True)
            return SubagentSynthesisResult(
                summary="synth",
                key_findings=["kf1"],
                risks=[],
                source_task_ids=["t1"],
                used_fallback=False,
            )

        with patch("safecode.agent.loop.findings_from_journal_events", return_value=[finding]):
            with patch("safecode.agent.loop.merge_subagent_findings", return_value=merged_mock):
                with patch("safecode.agent.loop.synthesize_findings", side_effect=fake_synthesize):
                    with patch.object(loop.journal, "read", return_value=[]):
                        context = loop._enrich_with_subagent_findings("session-1", {})

        assert len(synthesis_called_before) == 1
        assert "subagent_synthesis" in context
        assert context["subagent_synthesis"]["summary"] == "synth"


# ---------------------------------------------------------------------------
# Synthesis: output is redacted
# ---------------------------------------------------------------------------


class TestSynthesisOutputRedacted:
    def test_secret_in_summary_is_redacted(self):
        finding = _finding("t1", summary='api_key = "sk-secret12345678901234"')
        result = synthesize_findings([finding])
        assert "sk-secret" not in result.summary
        assert "[REDACTED]" in result.summary

    def test_secret_in_key_findings_is_redacted(self):
        finding = _finding(
            "t1",
            summary="clean",
            observations=['password = "hunter2"'],
        )
        result = synthesize_findings([finding])
        for kf in result.key_findings:
            assert "hunter2" not in kf

    def test_secret_in_risks_is_redacted(self):
        blocked = _finding(
            "t1",
            errors=['password = "hunter2supersecretvalue1234"'],
            blocked=True,
            success=False,
        )
        result = synthesize_findings([blocked])
        for risk in result.risks:
            assert "hunter2supersecretvalue1234" not in risk

    def test_llm_response_with_secret_is_redacted(self):
        client = _mock_llm_client(content='api_key="sk-secret98765" found in config.')
        finding = _finding("t1")
        result = synthesize_findings([finding], client)
        assert "sk-secret" not in result.summary


# ---------------------------------------------------------------------------
# Synthesis: empty findings
# ---------------------------------------------------------------------------


class TestSynthesisEmptyFindings:
    def test_empty_findings_returns_safe_result(self):
        result = synthesize_findings([])
        assert result.summary == ""
        assert result.key_findings == []
        assert result.risks == []
        assert result.source_task_ids == []
        assert result.used_fallback is True

    def test_all_blocked_findings_returns_fallback(self):
        blocked = [
            _finding("t1", blocked=True, success=False, errors=["blocked by policy"]),
            _finding("t2", blocked=True, success=False, errors=["another block"]),
        ]
        result = synthesize_findings(blocked)
        assert result.used_fallback is True
        assert result.source_task_ids == []

    def test_empty_with_llm_still_safe(self):
        client = _mock_llm_client("some synthesis")
        result = synthesize_findings([], client)
        assert result.summary == ""
        assert result.used_fallback is True
        client.ask.assert_not_called()


# ---------------------------------------------------------------------------
# Synthesis: failure fallback
# ---------------------------------------------------------------------------


class TestSynthesisFailureFallback:
    def test_llm_exception_falls_back_safely(self):
        client = MagicMock()
        client.ask.side_effect = RuntimeError("LLM unavailable")
        findings = [_finding("t1"), _finding("t2")]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = synthesize_findings(findings, client)

        assert result.used_fallback is True
        assert isinstance(result.summary, str)
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)

    def test_none_llm_client_uses_fallback(self):
        findings = [_finding("t1", summary="obs from t1")]
        result = synthesize_findings(findings, llm_client=None)
        assert result.used_fallback is True
        assert "obs from t1" in result.summary

    def test_fallback_preserves_merged_findings(self):
        """If synthesis fails, merged findings must still be available in context."""
        from unittest.mock import patch
        from safecode.agent.loop import AgentLoop
        from safecode.config import SafeCodeConfig

        with patch("safecode.agent.loop.SafeCodeConfig") as mock_cfg_cls:
            mock_cfg_cls.load.return_value = SafeCodeConfig()
            loop = AgentLoop(project_root=__import__("pathlib").Path("/tmp/test-synth-fallback"))

        merged_mock = MagicMock()
        merged_mock.source_task_ids = ["t1"]
        merged_mock.blocked_task_ids = []
        merged_mock.errors = []
        merged_mock.summary = "findings"
        merged_mock.observations = []
        merged_mock.files_inspected = []

        finding = _finding("t1", "findings")

        def fail_synthesize(*args, **kwargs):
            raise RuntimeError("synthesis exploded")

        with patch("safecode.agent.loop.findings_from_journal_events", return_value=[finding]):
            with patch("safecode.agent.loop.merge_subagent_findings", return_value=merged_mock):
                with patch("safecode.agent.loop.synthesize_findings", side_effect=fail_synthesize):
                    with patch.object(loop.journal, "read", return_value=[]):
                        with warnings.catch_warnings(record=True) as w:
                            warnings.simplefilter("always")
                            context = loop._enrich_with_subagent_findings("session-x", {})

        # Merged findings must still be in context despite synthesis failure.
        assert "subagent_findings" in context
        assert "subagent_synthesis" not in context
        assert any("synthesis failed" in str(warning.message) for warning in w)


# ---------------------------------------------------------------------------
# Synthesis: source task IDs are deterministic
# ---------------------------------------------------------------------------


class TestSynthesisSourceTaskIdsDeterministic:
    def test_source_ids_sorted(self):
        findings = [
            _finding("zzz-task"),
            _finding("aaa-task"),
            _finding("mmm-task"),
        ]
        result = synthesize_findings(findings)
        assert result.source_task_ids == sorted(result.source_task_ids)

    def test_blocked_tasks_not_in_source_ids(self):
        findings = [
            _finding("t-good", success=True, blocked=False),
            _finding("t-bad", success=False, blocked=True),
        ]
        result = synthesize_findings(findings)
        assert "t-bad" not in result.source_task_ids
        assert "t-good" in result.source_task_ids

    def test_source_ids_stable_across_calls(self):
        findings = [_finding("z-task"), _finding("a-task"), _finding("m-task")]
        ids1 = synthesize_findings(findings).source_task_ids
        ids2 = synthesize_findings(findings).source_task_ids
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# Synthesis: no real provider/network calls
# ---------------------------------------------------------------------------


class TestSynthesisNoRealNetworkCalls:
    def test_no_network_call_with_none_client(self):
        """synthesize_findings with no client never touches the network."""
        findings = [_finding("t1"), _finding("t2")]
        result = synthesize_findings(findings, llm_client=None)
        assert result.used_fallback is True

    def test_mock_client_not_real_provider(self):
        """Injected mock client is used; no real HTTP calls."""
        client = _mock_llm_client("Local mock synthesis text.")
        findings = [_finding("t1", "some finding")]
        result = synthesize_findings(findings, client)
        client.ask.assert_called_once()
        assert result.used_fallback is False

    def test_max_findings_limits_llm_input(self):
        """max_findings caps how many successful findings are sent to LLM."""
        call_args_store: list = []

        client = MagicMock()
        answer = MagicMock()
        answer.content = "summary\n- finding 1"

        def capture_ask(prompt, ctx):
            call_args_store.append(prompt)
            return answer

        client.ask.side_effect = capture_ask

        findings = [_finding(f"t{i}") for i in range(20)]
        synthesize_findings(findings, client, max_findings=3)

        assert len(call_args_store) == 1
        # Only up to 3 findings should appear in the prompt
        prompt = call_args_store[0]
        # Each finding has a "-" bullet; there should not be more than 3 bullets from tasks
        bullet_count = prompt.count("\n- ")
        assert bullet_count <= 3
