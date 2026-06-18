"""Single-use grant store tests."""

from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import (
    Action,
    Grant,
    GrantAlreadyConsumedError,
    consume_grant,
    save_grant,
)
from safecode.enterprise.workflow.exceptions import ApprovalRequestExistsError


def _grant(run_id: str = "run-grant0001", grant_id: str = "grant-run-grant0001") -> Grant:
    return Grant(
        grant_id=grant_id,
        run_id=run_id,
        request_id="approval-run-grant0001",
        action=Action.file_write,
        policy_snapshot_id="snapshot-test",
        created_at="2026-06-19T00:00:00+00:00",
    )


def test_grant_persist_and_consume_once(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    saved = save_grant(sac_root, _grant())
    assert saved.grant_hash
    consumed = consume_grant(sac_root, saved.run_id, saved.grant_id)
    assert consumed.consumed_at is not None


def test_second_consume_raises(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    saved = save_grant(sac_root, _grant())
    consume_grant(sac_root, saved.run_id, saved.grant_id)
    with pytest.raises(GrantAlreadyConsumedError):
        consume_grant(sac_root, saved.run_id, saved.grant_id)


def test_duplicate_grant_id_rejected(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    save_grant(sac_root, _grant())
    with pytest.raises(ApprovalRequestExistsError):
        save_grant(sac_root, _grant())
