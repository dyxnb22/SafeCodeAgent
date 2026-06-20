"""Keyed thread locks and cross-process exclusive file locks."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_thread_locks: dict[str, threading.RLock] = {}
_thread_locks_guard = threading.Lock()
_reentrant_depths = threading.local()


def _reset_lock_state_after_fork() -> None:
    """Discard inherited thread-only ownership state in a forked child."""
    global _thread_locks, _thread_locks_guard, _reentrant_depths
    _thread_locks = {}
    _thread_locks_guard = threading.Lock()
    _reentrant_depths = threading.local()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_lock_state_after_fork)


def lock_path_for(path: Path) -> Path:
    """Return a sibling lock file path that does not replace *path*."""
    return path.with_name(f"{path.name}.lock")


def _lock_file_identity(lock_file: Path) -> str:
    """Return the canonical in-process lock identity for *lock_file*."""
    parent = lock_file.parent.resolve()
    return str(parent / lock_file.name)


def _depth_map() -> dict[str, int]:
    depths = getattr(_reentrant_depths, "values", None)
    if depths is None:
        depths = {}
        _reentrant_depths.values = depths
    return depths


def _thread_lock(identity: str) -> threading.RLock:
    with _thread_locks_guard:
        lock = _thread_locks.get(identity)
        if lock is None:
            lock = threading.RLock()
            _thread_locks[identity] = lock
        return lock


@contextmanager
def keyed_exclusive_lock(key: str, lock_file: Path) -> Iterator[None]:
    """Exclusively lock a file, reentrantly within the owning thread.

    ``key`` is retained for caller compatibility. Lock ownership is determined
    by the canonical lock-file path so aliases cannot bypass in-process
    serialization merely by supplying different semantic keys.
    """
    _ = key
    identity = _lock_file_identity(lock_file)
    depths = _depth_map()
    current_depth = depths.get(identity, 0)
    if current_depth > 0:
        depths[identity] = current_depth + 1
        try:
            yield
        finally:
            next_depth = depths.get(identity, 1) - 1
            if next_depth <= 0:
                depths.pop(identity, None)
            else:
                depths[identity] = next_depth
        return

    thread_lock = _thread_lock(identity)
    thread_lock.acquire()
    try:
        with _cross_process_file_lock(lock_file):
            depths[identity] = 1
            try:
                yield
            finally:
                depths.pop(identity, None)
    finally:
        thread_lock.release()


@contextmanager
def _cross_process_file_lock(lock_file: Path) -> Iterator[None]:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    elif lock_file.is_symlink():
        raise OSError(f"refusing symlink lock file: {lock_file}")
    fd = os.open(lock_file, flags, 0o600)
    handle = os.fdopen(fd, "r+b", buffering=0)
    acquired = False
    try:
        if sys.platform == "win32" and lock_file.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        _acquire_exclusive(handle)
        acquired = True
        yield
    finally:
        try:
            if acquired:
                _release_exclusive(handle)
        finally:
            handle.close()


def _acquire_exclusive(handle) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    try:
        import fcntl
    except ImportError as exc:
        raise OSError(
            "fcntl is unavailable on this platform; exclusive file locks are required"
        ) from exc
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_exclusive(handle) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_replace_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace *path* with *content* using a unique same-directory temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
