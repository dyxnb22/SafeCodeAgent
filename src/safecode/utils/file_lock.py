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


def lock_path_for(path: Path) -> Path:
    """Return a sibling lock file path that does not replace *path*."""
    return path.with_name(f"{path.name}.lock")


def _thread_lock(key: str) -> threading.RLock:
    with _thread_locks_guard:
        lock = _thread_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _thread_locks[key] = lock
        return lock


@contextmanager
def keyed_exclusive_lock(key: str, lock_file: Path) -> Iterator[None]:
    """Acquire a keyed in-process lock and a cross-process exclusive file lock."""
    thread_lock = _thread_lock(key)
    thread_lock.acquire()
    try:
        with _cross_process_file_lock(lock_file):
            yield
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
