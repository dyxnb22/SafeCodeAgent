"""Timeline redaction tests."""

import asyncio
from pathlib import Path

from safecode.enterprise.trace.timeline import build_timeline, serialize_timeline
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType

SECRET_TOKEN = "ghp_" + ("x" * 36)


def test_timeline_json_has_no_verbatim_secrets(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-redact0001"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        extra={"note": SECRET_TOKEN},
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    payload = serialize_timeline(build_timeline(sac_root, run_id))
    assert SECRET_TOKEN not in payload
    assert "[REDACTED]" in payload or "redacted" in payload or "redaction_complete" in payload


def test_citation_excerpts_are_truncated_or_redacted(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-redact0002"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    timeline = build_timeline(sac_root, run_id)
    for citation in timeline.citations:
        assert len(citation.text_excerpt) <= 260
