"""Security, durability, and reentrancy tests for local file locking helpers."""

from __future__ import annotations

import multiprocessing
import threading
from pathlib import Path

import pytest

from safecode.utils.file_lock import atomic_replace_text, keyed_exclusive_lock


def test_exclusive_lock_refuses_symlink_lock_file(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("do-not-touch", encoding="utf-8")
    lock_file = tmp_path / "state.lock"
    lock_file.symlink_to(victim)

    with pytest.raises(OSError):
        with keyed_exclusive_lock("symlink-probe", lock_file):
            pytest.fail("symlink lock files must be rejected")

    assert victim.read_text(encoding="utf-8") == "do-not-touch"


def test_atomic_replace_does_not_reuse_predictable_temp_symlink(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("do-not-touch", encoding="utf-8")
    predictable = tmp_path / f".{target.name}.predictable.tmp"
    predictable.symlink_to(victim)

    atomic_replace_text(target, '{"ok": true}')

    assert target.read_text(encoding="utf-8") == '{"ok": true}'
    assert victim.read_text(encoding="utf-8") == "do-not-touch"
    assert predictable.is_symlink()


def test_nested_same_key_and_lock_file_completes(tmp_path: Path) -> None:
    lock_file = tmp_path / "state.lock"
    with keyed_exclusive_lock("outer", lock_file):
        with keyed_exclusive_lock("inner", lock_file):
            pass


def test_nested_different_keys_same_lock_file_share_identity(tmp_path: Path) -> None:
    lock_file = tmp_path / "shared.lock"
    with keyed_exclusive_lock("semantic-a", lock_file):
        with keyed_exclusive_lock("semantic-b", lock_file):
            pass


def test_nested_exception_releases_lock_for_later_acquisition(tmp_path: Path) -> None:
    lock_file = tmp_path / "state.lock"
    with pytest.raises(RuntimeError):
        with keyed_exclusive_lock("outer", lock_file):
            with keyed_exclusive_lock("inner", lock_file):
                raise RuntimeError("nested failure")
    with keyed_exclusive_lock("after-error", lock_file):
        pass


def test_second_thread_blocks_until_first_thread_releases(tmp_path: Path) -> None:
    lock_file = tmp_path / "state.lock"
    holder_acquired = threading.Event()
    waiter_started = threading.Event()
    release_holder = threading.Event()
    waiter_acquired = threading.Event()
    failures: list[BaseException] = []

    def hold_lock() -> None:
        try:
            with keyed_exclusive_lock("holder", lock_file):
                holder_acquired.set()
                if not release_holder.wait(timeout=2):
                    raise TimeoutError("test did not release holder")
        except BaseException as exc:  # pragma: no cover - asserted in parent
            failures.append(exc)

    def wait_for_lock() -> None:
        try:
            if not holder_acquired.wait(timeout=2):
                raise TimeoutError("holder did not acquire lock")
            waiter_started.set()
            with keyed_exclusive_lock("waiter", lock_file):
                waiter_acquired.set()
        except BaseException as exc:  # pragma: no cover - asserted in parent
            failures.append(exc)

    holder = threading.Thread(target=hold_lock)
    waiter = threading.Thread(target=wait_for_lock)
    holder.start()
    waiter.start()
    assert waiter_started.wait(timeout=2)
    assert waiter_acquired.wait(timeout=0.1) is False
    release_holder.set()
    holder.join(timeout=2)
    waiter.join(timeout=2)
    assert holder.is_alive() is False
    assert waiter.is_alive() is False
    assert failures == []
    assert waiter_acquired.is_set()


def _nested_reentrancy_child(lock_path: str, result_queue) -> None:
    lock_file = Path(lock_path)
    try:
        with keyed_exclusive_lock("outer-key", lock_file):
            with keyed_exclusive_lock("inner-key", lock_file):
                pass
        result_queue.put("ok")
    except Exception as exc:  # pragma: no cover - child failure path
        result_queue.put(f"error:{exc}")


def _acquire_lock_child(lock_path: str, started, acquired) -> None:
    started.set()
    with keyed_exclusive_lock("child", Path(lock_path)):
        acquired.set()


def test_nested_reentrancy_completes_in_spawned_child(tmp_path: Path) -> None:
    lock_file = tmp_path / "child.lock"
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    process = ctx.Process(
        target=_nested_reentrancy_child,
        args=(str(lock_file), result_queue),
    )
    process.start()
    process.join(timeout=5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=1)
        pytest.fail("nested keyed_exclusive_lock deadlocked in child process")
    assert process.exitcode == 0
    assert result_queue.get(timeout=1) == "ok"


def test_spawned_process_blocks_until_parent_releases(tmp_path: Path) -> None:
    lock_file = tmp_path / "process.lock"
    ctx = multiprocessing.get_context("spawn")
    started = ctx.Event()
    acquired = ctx.Event()
    process = ctx.Process(
        target=_acquire_lock_child,
        args=(str(lock_file), started, acquired),
    )

    try:
        with keyed_exclusive_lock("parent", lock_file):
            process.start()
            assert started.wait(timeout=5)
            assert acquired.wait(timeout=0.1) is False

        assert acquired.wait(timeout=5)
        process.join(timeout=5)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
    assert process.exitcode == 0


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="fork unavailable",
)
def test_forked_child_does_not_inherit_parent_reentrant_ownership(tmp_path: Path) -> None:
    lock_file = tmp_path / "fork.lock"
    ctx = multiprocessing.get_context("fork")
    started = ctx.Event()
    acquired = ctx.Event()
    process = ctx.Process(
        target=_acquire_lock_child,
        args=(str(lock_file), started, acquired),
    )

    try:
        with keyed_exclusive_lock("parent", lock_file):
            process.start()
            assert started.wait(timeout=5)
            assert acquired.wait(timeout=0.1) is False

        assert acquired.wait(timeout=5)
        process.join(timeout=5)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
    assert process.exitcode == 0
