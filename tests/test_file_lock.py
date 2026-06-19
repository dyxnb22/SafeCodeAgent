"""Security and durability tests for local file locking helpers."""

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
