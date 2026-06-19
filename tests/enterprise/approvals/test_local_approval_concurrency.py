"""Local approval store concurrency regression tests."""

from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
    GrantAlreadyConsumedError,
    RequestAlreadyConsumedError,
    consume_grant,
    decide_request,
    grant_hash,
    request_hash,
    save_grant,
    save_request,
)
from safecode.enterprise.workflow.types import RiskTier
from safecode.utils.time import utc_now_iso


def _pending_request(run_id: str, request_id: str) -> ApprovalRequest:
    request = ApprovalRequest(
        request_id=request_id,
        run_id=run_id,
        tenant_id="local",
        action=Action.file_write,
        risk_tier=RiskTier.high,
        requested_by_node="node",
        requesting_actor="user:security",
        policy_snapshot_id="snapshot-local",
        created_at=utc_now_iso(),
    )
    return request.model_copy(update={"request_hash": request_hash(request)})


def _grant(run_id: str, grant_id: str, request_id: str) -> Grant:
    grant = Grant(
        grant_id=grant_id,
        run_id=run_id,
        request_id=request_id,
        tenant_id="local",
        action=Action.file_write,
        policy_snapshot_id="snapshot-local",
        created_at=utc_now_iso(),
    )
    return grant.model_copy(update={"grant_hash": grant_hash(grant)})


def test_consume_grant_allows_one_winner_under_threads(tmp_path: Path) -> None:
    for iteration in range(10):
        sac_root = tmp_path / f"grant-thread-{iteration}" / ".sac"
        grant_id = f"grant-thread{iteration:02d}"
        saved = save_grant(
            sac_root,
            _grant("run-grantth01", grant_id, "approval-thread01"),
        )
        barrier = threading.Barrier(16)

        def consume_once() -> str:
            barrier.wait()
            try:
                consume_grant(sac_root, saved.run_id, saved.grant_id)
                return "ok"
            except GrantAlreadyConsumedError:
                return "consumed"

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = [future.result() for future in as_completed(pool.submit(consume_once) for _ in range(16))]
        assert results.count("ok") == 1
        assert results.count("consumed") == 15


def test_decide_request_allows_one_terminal_decision(tmp_path: Path) -> None:
    run_id = "run-decideth01"
    for iteration in range(10):
        sac_root = tmp_path / f"decide-thread-{iteration}" / ".sac"
        request_id = f"approval-decide{iteration:02d}"
        save_request(sac_root, _pending_request(run_id, request_id))
        barrier = threading.Barrier(12)

        def decide_once(decision: str) -> str:
            barrier.wait()
            try:
                decide_request(
                    sac_root,
                    run_id,
                    request_id,
                    decision=decision,
                    decision_actor="user:approver",
                )
                return "ok"
            except RequestAlreadyConsumedError:
                return "consumed"

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = [
                future.result()
                for future in as_completed(
                    pool.submit(decide_once, "approved" if index % 2 == 0 else "rejected")
                    for index in range(12)
                )
            ]
        assert results.count("ok") == 1
        assert results.count("consumed") == 11


def _mp_consume_worker(sac_root: str, run_id: str, grant_id: str, ready, results) -> None:
    ready.wait()
    try:
        consume_grant(Path(sac_root), run_id, grant_id)
        results.append("ok")
    except GrantAlreadyConsumedError:
        results.append("consumed")


def test_consume_grant_multiprocess_single_winner(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    for iteration in range(10):
        sac_root = tmp_path / f"grant-mp-{iteration}" / ".sac"
        grant_id = f"grant-mp{iteration:06d}"
        saved = save_grant(
            sac_root,
            _grant("run-grantmp01", grant_id, "approval-mp01"),
        )
        manager = ctx.Manager()
        ready = ctx.Barrier(8)
        results = manager.list()
        processes = [
            ctx.Process(
                target=_mp_consume_worker,
                args=(str(sac_root), saved.run_id, saved.grant_id, ready, results),
            )
            for _ in range(8)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        assert results.count("ok") == 1
        assert results.count("consumed") == 7
