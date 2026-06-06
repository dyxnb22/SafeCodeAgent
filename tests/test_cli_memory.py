"""Tests for v4.6.0 experimental sac memory CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.memory.facade import MemoryFacade

runner = CliRunner()


def test_memory_help_accessible() -> None:
    result = runner.invoke(app, ["memory", "--help"])

    assert result.exit_code == 0
    assert "show" in result.output
    assert "pin" in result.output


def test_add_note_and_show_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["memory", "add-note", "keep parser deterministic"])
    shown = runner.invoke(app, ["memory", "show", "--project"])

    assert result.exit_code == 0
    assert shown.exit_code == 0
    assert "keep parser deterministic" in shown.output


def test_add_note_task_json_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["memory", "add-note", "task note", "--task-id", "abc", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "memory add-note"
    assert data["status"] == "success"
    assert data["data"]["task_id"] == "abc"


def test_show_task_requires_task_id_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["memory", "show", "--task", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["status"] == "error"
    assert "--task-id" in data["error"]


def test_pin_unpin_and_show_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    pin = runner.invoke(app, ["memory", "pin", "./src/app.py", "--json"])
    shown = runner.invoke(app, ["memory", "show", "--pinned", "--json"])
    unpin = runner.invoke(app, ["memory", "unpin", "src/app.py", "--json"])

    assert pin.exit_code == 0
    assert json.loads(pin.output)["data"]["path"] == "src/app.py"
    assert json.loads(shown.output)["data"]["pinned_files"] == ["src/app.py"]
    assert unpin.exit_code == 0
    assert MemoryFacade(tmp_path).read_pinned_files() == []


def test_pin_outside_root_refused_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["memory", "pin", str(tmp_path.parent / "outside.py"), "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["status"] == "error"
    assert "project root" in data["error"]


def test_show_recent_failures_json_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    MemoryFacade(tmp_path).record_failure(
        task_id="t",
        command="pytest",
        exit_code=1,
        tail="Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    )

    result = runner.invoke(app, ["memory", "show", "--recent-failures", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "memory show"
    assert payload["data"]["entries"][0]["tail_summary"] == "Authorization: Bearer [REDACTED]"


def test_clear_requires_yes_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    MemoryFacade(tmp_path).add_note("note")

    result = runner.invoke(app, ["memory", "clear", "--project"], input="n\n")

    assert result.exit_code == 0
    assert MemoryFacade(tmp_path).read_project_notes().strip() == "note"


def test_clear_project_with_yes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    MemoryFacade(tmp_path).add_note("note")

    result = runner.invoke(app, ["memory", "clear", "--project", "--yes", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "success"
    assert MemoryFacade(tmp_path).read_project_notes() == ""
