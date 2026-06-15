"""Context compaction for long agent sessions (v5.3.1).

When accumulated tool-result context in a session would push the next LLM call
over 60% of the context window, this module triggers compaction: asks the model
to summarise what it has learned, then replaces the raw tool results with the
compact summary.

Original observations are never discarded — they are archived to
.sac/sessions/<session_id>/observations_compacted_<N>.jsonl.

Safety: compaction itself costs one LLM call; recorded as audit event
tool_call_compact with token counts.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from safecode.agent.native_tools import NativeToolResult


_DEFAULT_THRESHOLD_RATIO = 0.60  # trigger at 60% of estimated context budget
_DEFAULT_MAX_TOKENS = 40_000     # fallback context window estimate
_SUMMARY_MAX_CHARS = 8_000       # max length of the compaction summary prompt
_SUMMARY_TARGET_TOKENS = 2000    # instruction to model for summary length
_CHARS_PER_TOKEN_ESTIMATE = 4    # rough estimate for token counting


@dataclass
class CompactionResult:
    """Result of one compaction operation."""
    summary: str
    observations_archived: int
    tokens_before: int
    tokens_after: int
    compaction_index: int  # N in observations_compacted_N.jsonl


class ContextCompactor:
    """Compact accumulated tool-result context when it exceeds a threshold (v5.3.1).

    Usage::

        compactor = ContextCompactor(llm_client, project_root, session_id)
        if compactor.should_compact(current_token_estimate):
            result = compactor.compact(observations)
    """

    def __init__(
        self,
        llm_client: Any,
        project_root: Path,
        session_id: str,
        *,
        threshold_ratio: float = _DEFAULT_THRESHOLD_RATIO,
        max_context_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self.llm_client = llm_client
        self.project_root = project_root
        self.session_id = session_id
        self.threshold_ratio = threshold_ratio
        self.max_context_tokens = max_context_tokens
        self._compaction_count = 0

    def should_compact(self, current_token_estimate: int) -> bool:
        """Return True when current_token_estimate exceeds the threshold."""
        threshold = int(self.threshold_ratio * self.max_context_tokens)
        return current_token_estimate >= threshold

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate from character count."""
        return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)

    def compact(self, observations: list[str]) -> CompactionResult:
        """Summarise observations and archive the originals.

        Returns CompactionResult with the summary text.
        Raises RuntimeError if the LLM call fails — callers should catch and skip.
        """
        self._compaction_count += 1
        combined = "\n\n".join(observations)
        tokens_before = self.estimate_tokens(combined)

        # Truncate input to avoid blowing the model's context
        truncated = combined[:_SUMMARY_MAX_CHARS]
        if len(combined) > _SUMMARY_MAX_CHARS:
            truncated += f"\n[... {len(combined) - _SUMMARY_MAX_CHARS} chars truncated ...]"

        prompt = (
            f"Summarise the following tool results from an agent coding session. "
            f"Preserve: key findings, file paths inspected, edits proposed or applied, "
            f"test results, errors encountered. Target: under {_SUMMARY_TARGET_TOKENS} tokens.\n\n"
            + truncated
        )

        # Use the LLM client to produce the summary
        try:
            answer = self.llm_client.ask(prompt, {})
            summary = getattr(answer, "content", None) or str(answer)
        except Exception as exc:
            raise RuntimeError(f"Compaction LLM call failed: {type(exc).__name__}: {exc}") from exc

        tokens_after = self.estimate_tokens(summary)

        # Archive original observations
        self._archive_observations(observations)

        # Emit audit event for the compaction
        self._audit_compact(tokens_before, tokens_after, len(observations))

        return CompactionResult(
            summary=summary,
            observations_archived=len(observations),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            compaction_index=self._compaction_count,
        )

    def _archive_observations(self, observations: list[str]) -> None:
        """Write original observations to .sac/sessions/<id>/observations_compacted_<N>.jsonl."""
        try:
            sessions_dir = self.project_root / ".sac" / "sessions" / self.session_id
            sessions_dir.mkdir(parents=True, exist_ok=True)
            archive_path = sessions_dir / f"observations_compacted_{self._compaction_count}.jsonl"
            with archive_path.open("w", encoding="utf-8") as f:
                for obs in observations:
                    f.write(json.dumps({"observation": obs}) + "\n")
        except OSError as exc:
            warnings.warn(
                f"compaction archive write failed: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )

    def _audit_compact(self, tokens_before: int, tokens_after: int, obs_count: int) -> None:
        """Record audit event for the compaction."""
        try:
            from safecode.audit.logger import AuditLogger
            from safecode.audit.models import AuditEvent
            from safecode.utils.time import utc_now_iso
            from safecode.config import SafeCodeConfig

            config = SafeCodeConfig.load(self.project_root)
            AuditLogger(self.project_root, config).write(
                AuditEvent(
                    type="tool_call_compact",
                    timestamp=utc_now_iso(),
                    message=f"Context compacted: {tokens_before} → {tokens_after} estimated tokens",
                    metadata={
                        "session_id": self.session_id,
                        "observations_count": str(obs_count),
                        "tokens_before": str(tokens_before),
                        "tokens_after": str(tokens_after),
                        "compaction_index": str(self._compaction_count),
                    },
                )
            )
        except Exception:
            pass  # Audit failure is non-fatal
