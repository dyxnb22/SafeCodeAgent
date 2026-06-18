"""Markdown dashboard section tests."""

import asyncio
from pathlib import Path

from safecode.enterprise.trace.render_markdown import markdown_sections, render_markdown
from safecode.enterprise.trace.timeline import build_timeline
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType

REQUIRED_SECTIONS = [
    "## Summary",
    "## Timeline",
    "## Citations",
    "## Tool Calls",
    "## Approvals",
    "## Validation",
    "## Cost and Token Summary",
    "## Safety Invariants",
    "## Failures",
]


def test_render_markdown_includes_all_sections(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    run_id = "run-render0001"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    timeline = build_timeline(sac_root, run_id)
    markdown = render_markdown(timeline)
    for section in REQUIRED_SECTIONS:
        assert section in markdown
    assert markdown_sections(timeline) == [
        "Summary",
        "Timeline",
        "Citations",
        "Tool Calls",
        "Approvals",
        "Validation",
        "Cost and Token Summary",
        "Safety Invariants",
        "Failures",
    ]
