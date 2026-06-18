"""CLI approval revoke and evidence request tests."""

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.approvals.store import Action, ApprovalRequest, load_request, save_request
from safecode.enterprise.workflow.types import RiskTier


def _seed_request(tmp_path: Path) -> tuple[str, str]:
    run_id = "run-revoke001"
    request_id = "approval-run-revoke001"
    sac_root = tmp_path / ".sac"
    save_request(
        sac_root,
        ApprovalRequest(
            request_id=request_id,
            run_id=run_id,
            action=Action.github_pr_create,
            risk_tier=RiskTier.high,
            requested_by_node="approval_gate",
            requesting_actor="user:test",
            policy_snapshot_id="snapshot-local",
            created_at="2026-06-19T00:00:00+00:00",
        ),
    )
    return run_id, request_id


def test_request_evidence_updates_status(tmp_path: Path):
    run_id, request_id = _seed_request(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "approval",
            "request-evidence",
            run_id,
            request_id,
            "--actor",
            "user:reviewer",
            "--note",
            "need threat model",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "evidence_requested"


def test_revoke_pending_request(tmp_path: Path):
    run_id, request_id = _seed_request(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "approval",
            "revoke",
            run_id,
            request_id,
            "--actor",
            "user:reviewer",
            "--reason",
            "superseded",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "revoked"
    loaded = load_request(tmp_path / ".sac", run_id, request_id)
    assert loaded.status == "revoked"


def test_reject_with_reason(tmp_path: Path):
    run_id, request_id = _seed_request(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "approval",
            "reject",
            run_id,
            request_id,
            "--actor",
            "user:reviewer",
            "--reason",
            "too risky",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    loaded = load_request(tmp_path / ".sac", run_id, request_id)
    assert loaded.status == "rejected"
    assert loaded.decision_note == "too risky"
