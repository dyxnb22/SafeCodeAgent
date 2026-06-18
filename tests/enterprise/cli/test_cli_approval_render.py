"""CLI approval markdown render tests."""

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.approvals.store import Action, ApprovalRequest, save_request
from safecode.enterprise.workflow.types import RiskTier


def _seed_request(tmp_path: Path) -> tuple[str, str]:
    run_id = "run-render001"
    request_id = "approval-run-render001"
    sac_root = tmp_path / ".sac"
    request = ApprovalRequest(
        request_id=request_id,
        run_id=run_id,
        action=Action.file_write,
        risk_tier=RiskTier.high,
        requested_by_node="approval_gate",
        requesting_actor="user:test",
        policy_snapshot_id="snapshot-local",
        created_at="2026-06-19T00:00:00+00:00",
    )
    save_request(sac_root, request)
    return run_id, request_id


def test_list_pending_filters_and_markdown_render(tmp_path: Path):
    run_id, _ = _seed_request(tmp_path)
    runner = CliRunner()
    pending_json = runner.invoke(
        enterprise_app,
        ["approval", "list", run_id, "--pending", "--root", str(tmp_path)],
    )
    assert pending_json.exit_code == 0
    assert len(json.loads(pending_json.stdout)) == 1

    markdown = runner.invoke(
        enterprise_app,
        ["approval", "list", run_id, "--pending", "--markdown", "--root", str(tmp_path)],
    )
    assert markdown.exit_code == 0
    assert "# Pending Approvals" in markdown.stdout
    assert "approval-run-render001" in markdown.stdout
    assert "file_write" in markdown.stdout


def test_approve_with_note(tmp_path: Path):
    run_id, request_id = _seed_request(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "approval",
            "approve",
            run_id,
            request_id,
            "--actor",
            "user:approver",
            "--note",
            "looks good",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "approved"
