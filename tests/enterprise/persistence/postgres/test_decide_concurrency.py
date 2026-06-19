"""PostgreSQL approval decision concurrency tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from safecode.enterprise.approvals.store import Action, ApprovalRequest, request_hash
from safecode.enterprise.workflow.exceptions import RequestAlreadyConsumedError
from safecode.enterprise.workflow.types import RiskTier
from safecode.utils.time import utc_now_iso

pytestmark = pytest.mark.postgres_integration


def _pending_request(run_id: str, request_id: str) -> ApprovalRequest:
    request = ApprovalRequest(
        request_id=request_id,
        run_id=run_id,
        tenant_id="tenant-a",
        action=Action.file_write,
        risk_tier=RiskTier.high,
        requested_by_node="node",
        requesting_actor="user:security",
        policy_snapshot_id="snapshot-local",
        created_at=utc_now_iso(),
    )
    return request.model_copy(update={"request_hash": request_hash(request)})


def test_parallel_decide_request_allows_one_winner(postgres_backend) -> None:
    store = postgres_backend.approvals
    run_id = "run-decidepg01"
    barrier = __import__("threading").Barrier(16)

    def decide_once(request_id: str, decision: str) -> str:
        barrier.wait()
        try:
            store.decide_request(
                tenant_id="tenant-a",
                run_id=run_id,
                request_id=request_id,
                decision=decision,
                decision_actor="user:approver",
            )
            return "ok"
        except RequestAlreadyConsumedError:
            return "consumed"

    for iteration in range(10):
        request_id = f"approval-decide-pg{iteration:02d}"
        store.save_request(tenant_id="tenant-a", request=_pending_request(run_id, request_id))
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [
                pool.submit(
                    decide_once,
                    request_id,
                    "approved" if index % 2 == 0 else "rejected",
                )
                for index in range(16)
            ]
            results = [future.result() for future in as_completed(futures)]
        assert results.count("ok") == 1
        assert results.count("consumed") == 15
