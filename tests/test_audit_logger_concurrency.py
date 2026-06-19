"""Concurrency regression tests for local audit hash-chain writes."""

from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.utils.time import utc_now_iso


def _write_one(logger: AuditLogger, index: int, barrier: threading.Barrier) -> None:
    barrier.wait()
    logger.write(
        AuditEvent(
            type=f"concurrent_event_{index}",
            timestamp=utc_now_iso(),
            message=f"event-{index}",
        )
    )


def _assert_linear_chain(logger: AuditLogger, expected_count: int) -> None:
    events = logger.iter_events()
    assert len(events) == expected_count
    previous: str | None = None
    for event in events:
        assert event.previous_hash == previous
        assert event.event_hash
        previous = event.event_hash
    ok, message = logger.verify_integrity()
    assert ok, message
    anchor = logger.anchor_store.latest(logger.log_file)
    assert anchor is not None
    assert anchor.line_count == expected_count
    assert anchor.event_hash == previous


def test_audit_logger_threaded_writes_remain_linear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
    workers = 12
    for iteration in range(10):
        root = tmp_path / f"thread-{iteration}"
        logger = AuditLogger(root)
        barrier = threading.Barrier(workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_write_one, logger, index, barrier) for index in range(workers)
            ]
            for future in as_completed(futures):
                future.result()
        _assert_linear_chain(logger, workers)


def _mp_write_worker(project_root: str, index: int, ready: multiprocessing.Barrier) -> None:
    logger = AuditLogger(Path(project_root))
    ready.wait()
    logger.write(
        AuditEvent(
            type=f"mp_event_{index}",
            timestamp=utc_now_iso(),
            message=f"mp-{index}",
        )
    )


def test_audit_logger_multiprocess_writes_remain_linear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
    workers = 8
    ctx = multiprocessing.get_context("spawn")
    for iteration in range(10):
        root = tmp_path / f"mp-{iteration}"
        ready = ctx.Barrier(workers)
        processes = [
            ctx.Process(
                target=_mp_write_worker,
                args=(str(root), index, ready),
            )
            for index in range(workers)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        _assert_linear_chain(AuditLogger(root), workers)


def test_verify_integrity_observes_consistent_snapshots_during_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
    root = tmp_path / "verify-during-write"
    logger = AuditLogger(root)
    started = threading.Event()
    finished = threading.Event()

    def write_many() -> None:
        started.set()
        for index in range(40):
            logger.write(
                AuditEvent(
                    type=f"verify_event_{index}",
                    timestamp=utc_now_iso(),
                )
            )
        finished.set()

    writer = threading.Thread(target=write_many)
    writer.start()
    assert started.wait(timeout=5)
    observations: list[tuple[bool, str]] = []
    while not finished.is_set():
        observations.append(logger.verify_integrity())
    writer.join(timeout=30)
    assert not writer.is_alive()
    observations.append(logger.verify_integrity())

    assert observations
    assert all(ok for ok, _message in observations), observations
    _assert_linear_chain(logger, 40)
