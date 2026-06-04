"""Tests for v4.6.0 unified memory facade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.memory.facade import MemoryFacade
from safecode.memory.store import MemoryStore
from safecode.project.rules import ProjectRules
from safecode.state.progress import ProgressState, ProgressStore


def test_reads_legacy_memory_progress_and_rules(tmp_path: Path) -> None:
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "memory.json").write_text(json.dumps({"framework": "fastapi"}), encoding="utf-8")
    ProgressStore(tmp_path).write(ProgressState(goal="ship", completed=["a"], next_steps=["b"], blockers=[]))
    ProjectRules(tmp_path).ensure()

    text = MemoryFacade(tmp_path).read_project_notes()

    assert "framework: fastapi" in text
    assert "SafeCode Progress" in text
    assert "SafeCode Project Rules" in text


def test_new_notes_write_only_to_new_project_layout(tmp_path: Path) -> None:
    facade = MemoryFacade(tmp_path)

    path = facade.add_note("health route must stay synchronous")

    assert path == tmp_path / ".sac" / "memory" / "project.md"
    assert "health route" in path.read_text(encoding="utf-8")
    assert not (tmp_path / ".sac" / "memory.json").exists()


def test_legacy_store_writes_to_new_layout(tmp_path: Path) -> None:
    MemoryStore(tmp_path).remember("style", "small diffs")

    assert "- style: small diffs" in (tmp_path / ".sac" / "memory" / "project.md").read_text(encoding="utf-8")
    assert not (tmp_path / ".sac" / "memory.json").exists()


def test_task_notes_write_to_per_task_memory(tmp_path: Path) -> None:
    path = MemoryFacade(tmp_path).add_note("retry parser edge case", task_id="fix-parser")

    assert path == tmp_path / ".sac" / "tasks" / "fix-parser" / "memory.md"
    assert "retry parser" in MemoryFacade(tmp_path).read_task_notes("fix-parser")


def test_recent_failures_are_capped_to_200_and_newest_first(tmp_path: Path) -> None:
    facade = MemoryFacade(tmp_path)
    for index in range(205):
        facade.record_failure(task_id="t", command=f"pytest {index}", exit_code=1, tail=f"tail {index}")

    entries = facade.read_recent_failures()

    assert len(entries) == 200
    assert entries[0]["command"] == "pytest 204"
    assert entries[-1]["command"] == "pytest 5"


def test_recent_edits_are_capped_to_200(tmp_path: Path) -> None:
    facade = MemoryFacade(tmp_path)
    for index in range(205):
        facade.record_edit({"path": f"file{index}.py"})

    entries = facade.read_recent_edits()

    assert len(entries) == 200
    assert entries[0]["path"] == "file204.py"


def test_reads_are_redacted(tmp_path: Path) -> None:
    token = "ghp_abcdefghijklmnop1234567890abcdef"
    MemoryFacade(tmp_path).project_path.parent.mkdir(parents=True)
    MemoryFacade(tmp_path).project_path.write_text(f"token {token}", encoding="utf-8")

    assert token not in MemoryFacade(tmp_path).read_project_notes()


def test_writes_reject_obvious_secrets(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        MemoryFacade(tmp_path).add_note("api_key=secret-value")


def test_pinned_paths_are_normalized_sorted_unique(tmp_path: Path) -> None:
    facade = MemoryFacade(tmp_path)

    facade.pin_file("b.py")
    facade.pin_file("./a.py")
    facade.pin_file("b.py")

    assert facade.read_pinned_files() == ["a.py", "b.py"]


def test_pinned_paths_refuse_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"

    with pytest.raises(ValueError):
        MemoryFacade(tmp_path).pin_file(outside)


def test_missing_pinned_files_are_allowed(tmp_path: Path) -> None:
    pinned = MemoryFacade(tmp_path).pin_file("missing.py")

    assert pinned == "missing.py"
    assert MemoryFacade(tmp_path).read_pinned_files() == ["missing.py"]
