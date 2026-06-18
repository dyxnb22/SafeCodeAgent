"""Timeline serializer round-trip and redaction tests."""

import asyncio
from pathlib import Path

from safecode.enterprise.trace.timeline import (
    TIMELINE_SCHEMA_VERSION,
    build_timeline,
    serialize_timeline,
    timeline_content_hash,
    write_timeline,
)
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType


def test_two_serializations_are_byte_identical(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-timeline001"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))

    first = build_timeline(sac_root, run_id)
    second = build_timeline(sac_root, run_id)
    assert serialize_timeline(first) == serialize_timeline(second)
    assert timeline_content_hash(first) == timeline_content_hash(second)

    path = write_timeline(sac_root, run_id)
    assert path.read_text(encoding="utf-8") == serialize_timeline(first)


def test_timeline_has_schema_version_and_nodes(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-timeline002"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    timeline = build_timeline(sac_root, run_id)
    assert timeline.timeline_schema_version == TIMELINE_SCHEMA_VERSION
    assert timeline.run_id == run_id
    assert len(timeline.nodes) == 9
    assert timeline.safety_invariants.redaction_complete is True
