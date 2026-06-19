"""Concurrent grant consumption tests against real PostgreSQL (v2.1.3-T3)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from safecode.enterprise.approvals.store import Action, Grant, GrantAlreadyConsumedError

pytestmark = pytest.mark.postgres_integration


def _grant(run_id: str = "run-grantconc01", grant_id: str = "grant-run-grantconc01") -> Grant:
    return Grant(
        grant_id=grant_id,
        run_id=run_id,
        request_id="approval-run-grantconc01",
        tenant_id="tenant-a",
        action=Action.file_write,
        policy_snapshot_id="snapshot-local",
        created_at="2026-06-19T00:00:00+00:00",
    )


def test_serializable_grant_consumption_allows_one_winner(postgres_backend) -> None:
    store = postgres_backend.approvals
    saved = store.save_grant(tenant_id="tenant-a", grant=_grant())
    successes = 0
    failures = 0

    def consume_once() -> None:
        nonlocal successes, failures
        try:
            store.consume_grant(
                tenant_id="tenant-a",
                run_id=saved.run_id,
                grant_id=saved.grant_id,
            )
            successes += 1
        except GrantAlreadyConsumedError:
            failures += 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(consume_once) for _ in range(16)]
        for future in as_completed(futures):
            future.result()

    assert successes == 1
    assert failures == 15


def test_retry_consume_after_success_fails_closed(postgres_backend) -> None:
    store = postgres_backend.approvals
    saved = store.save_grant(tenant_id="tenant-a", grant=_grant())
    store.consume_grant(
        tenant_id="tenant-a",
        run_id=saved.run_id,
        grant_id=saved.grant_id,
    )
    with pytest.raises(GrantAlreadyConsumedError):
        store.consume_grant(
            tenant_id="tenant-a",
            run_id=saved.run_id,
            grant_id=saved.grant_id,
        )
