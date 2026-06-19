"""GitHub PR comment writer approval gate tests."""

import json
from pathlib import Path

from safecode.enterprise.connectors.github_pr_write import PRCommentWriteSpec, post_pr_comment


def test_live_write_without_approval_is_blocked(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    record = post_pr_comment(
        sac_root=sac_root,
        run_id="run-gate00000001",
        node_name="finalize",
        spec=PRCommentWriteSpec(mode="live"),
        body="Please fix SQL injection",
        approved=False,
        actor_id="user:test",
    )
    assert record.outcome == "blocked"
    assert record.tool_name == "github_write"


def test_fixture_write_persists_redacted_body(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    out = tmp_path / "comment.md"
    body = "Rotate key ghp_1234567890123456789012345678901234"
    record = post_pr_comment(
        sac_root=sac_root,
        run_id="run-gate00000002",
        node_name="finalize",
        spec=PRCommentWriteSpec(mode="fixture", output_path=str(out)),
        body=body,
        approved=False,
        actor_id="user:test",
    )
    assert record.outcome == "ok"
    written = out.read_text(encoding="utf-8")
    assert "ghp_" not in written
    trace_path = sac_root / "enterprise" / "runs" / "run-gate00000002" / "trace.jsonl"
    assert trace_path.is_file()
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
    assert any(
        event.get("type") == "tool.executed" and event.get("payload", {}).get("tool_name") == "github_write"
        for event in events
    )


def test_live_write_with_approval_records_trace(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    record = post_pr_comment(
        sac_root=sac_root,
        run_id="run-gate00000003",
        node_name="finalize",
        spec=PRCommentWriteSpec(mode="live"),
        body="approved comment",
        approved=True,
        actor_id="user:approver",
    )
    assert record.outcome == "ok"
    trace_path = sac_root / "enterprise" / "runs" / "run-gate00000003" / "trace.jsonl"
    payload = trace_path.read_text(encoding="utf-8")
    assert "github_write" in payload
