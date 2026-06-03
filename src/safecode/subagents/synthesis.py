"""Parent-side synthesis of merged subagent findings (T-3.4.2-A).

The parent calls ``synthesize_findings`` before consuming the merged
subagent finding list. Synthesis output is redacted before return.
If synthesis fails (LLM unavailable, call error, or parse error), the
function falls back to a deterministic extraction from the raw findings
without raising. Never mutates the input findings list.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

from safecode.context.redactor import redact_secrets
from safecode.subagents.merge_policy import SubagentFinding

_DEFAULT_MAX_FINDINGS: int = 10


@dataclass(frozen=True)
class SubagentSynthesisResult:
    """Structured parent-side synthesis of merged subagent findings.

    Fields
    ------
    summary:
        Concise synthesised narrative across all successful findings.
    key_findings:
        Bullet-point key observations extracted from the synthesis.
    risks:
        Identified risks or errors from blocked/failed tasks.
    source_task_ids:
        Task IDs of successful findings that contributed to this synthesis,
        sorted for determinism.
    used_fallback:
        True when the LLM synthesis path was unavailable or failed and a
        deterministic local extraction was used instead.
    """

    summary: str
    key_findings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    source_task_ids: list[str] = field(default_factory=list)
    used_fallback: bool = False


def synthesize_findings(
    findings: list[SubagentFinding],
    llm_client: object | None = None,
    *,
    max_findings: int = _DEFAULT_MAX_FINDINGS,
) -> SubagentSynthesisResult:
    """Synthesise subagent findings into a structured summary.

    Synthesis output is redacted via ``redact_secrets`` before return.
    The original ``findings`` list is never mutated.
    If ``llm_client`` is None or the LLM call fails, the function falls
    back to a deterministic local extraction and sets ``used_fallback=True``.
    Never raises.

    Args:
        findings: Raw SubagentFinding objects from the current session.
        llm_client: Optional LLM client with an ``ask(question, context)``
            method returning an object with a ``content: str`` attribute.
            When None, the local fallback is used directly.
        max_findings: Maximum number of successful findings to include in
            the synthesis prompt or fallback extraction.
    """
    if not findings:
        return SubagentSynthesisResult(
            summary="",
            key_findings=[],
            risks=[],
            source_task_ids=[],
            used_fallback=True,
        )

    successful = [f for f in findings if f.success and not f.blocked][:max_findings]
    blocked = [f for f in findings if f.blocked or not f.success]

    if llm_client is not None and successful:
        try:
            result = _llm_synthesize(successful, blocked, llm_client)
            return _redact_result(result)
        except Exception as exc:
            warnings.warn(
                f"Subagent synthesis LLM call failed ({type(exc).__name__}); "
                "using local fallback.",
                RuntimeWarning,
                stacklevel=2,
            )

    return _redact_result(_fallback_synthesize(successful, blocked))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _llm_synthesize(
    successful: list[SubagentFinding],
    blocked: list[SubagentFinding],
    llm_client: object,
) -> SubagentSynthesisResult:
    """Call the LLM client to produce a synthesis summary."""
    findings_text = _format_findings_for_prompt(successful)
    prompt = (
        "Summarise the following subagent investigation findings. "
        "Respond with a concise summary paragraph followed by a bullet list "
        "of key findings. Do not include file names or paths verbatim.\n\n"
        f"Findings:\n{findings_text}"
    )
    answer = llm_client.ask(prompt, {"role": "synthesis"})
    content: str = getattr(answer, "content", str(answer)) or ""
    return _parse_llm_response(content, successful, blocked)


def _format_findings_for_prompt(findings: list[SubagentFinding]) -> str:
    parts: list[str] = []
    for f in findings:
        obs_text = "; ".join(f.observations[:5]) if f.observations else "(none)"
        parts.append(f"- {f.summary} [observations: {obs_text}]")
    return "\n".join(parts) if parts else "(no findings)"


def _parse_llm_response(
    content: str,
    successful: list[SubagentFinding],
    blocked: list[SubagentFinding],
) -> SubagentSynthesisResult:
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    summary_parts: list[str] = []
    bullet_parts: list[str] = []
    for ln in lines:
        if ln.startswith("- ") or ln.startswith("* "):
            bullet_parts.append(ln.lstrip("- *").strip())
        else:
            summary_parts.append(ln)
    summary = " ".join(summary_parts[:3])[:500] or content[:200]
    key_findings = bullet_parts[:10] or (
        [f.summary[:200] for f in successful[:5] if f.summary]
    )
    risks = [e for f in blocked for e in (f.errors or []) if e][:10]
    source_ids = sorted(f.task_id for f in successful if f.task_id)
    return SubagentSynthesisResult(
        summary=summary,
        key_findings=key_findings,
        risks=risks,
        source_task_ids=source_ids,
        used_fallback=False,
    )


def _fallback_synthesize(
    successful: list[SubagentFinding],
    blocked: list[SubagentFinding],
) -> SubagentSynthesisResult:
    """Deterministic local extraction when LLM is unavailable."""
    summary_parts = [f.summary for f in successful if f.summary]
    summary = "; ".join(summary_parts[:5])[:500]
    key_findings = [
        obs
        for f in successful
        for obs in (f.observations or [])
        if obs
    ][:10]
    risks = [e for f in blocked for e in (f.errors or []) if e][:10]
    source_ids = sorted(f.task_id for f in successful if f.task_id)
    return SubagentSynthesisResult(
        summary=summary,
        key_findings=key_findings,
        risks=risks,
        source_task_ids=source_ids,
        used_fallback=True,
    )


def _redact_result(result: SubagentSynthesisResult) -> SubagentSynthesisResult:
    """Return a new SubagentSynthesisResult with all text fields redacted."""
    return SubagentSynthesisResult(
        summary=redact_secrets(result.summary),
        key_findings=[redact_secrets(kf) for kf in result.key_findings],
        risks=[redact_secrets(r) for r in result.risks],
        source_task_ids=list(result.source_task_ids),
        used_fallback=result.used_fallback,
    )
