"""Tests for sac memory size and compute_sac_size (v4.19.1, EXPERIMENTAL)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli_memory import memory_app
from safecode.memory.sizing import compute_sac_size

runner = CliRunner()


def _invoke(tmp_path: Path, monkeypatch, *args: str):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(memory_app, list(args), catch_exceptions=False)


# ---------------------------------------------------------------------------
# Unit tests for compute_sac_size
# ---------------------------------------------------------------------------


def test_sac_missing(tmp_path: Path):
    report = compute_sac_size(tmp_path)
    assert report.exists is False
    assert report.total_bytes == 0
    assert report.total_files == 0
    assert report.scopes == []
    assert report.experimental is True


def test_sac_empty_dir(tmp_path: Path):
    sac = tmp_path / ".sac"
    sac.mkdir()
    report = compute_sac_size(tmp_path)
    assert report.exists is True
    assert report.total_bytes == 0
    assert report.total_files == 0
    named = {e.name: e for e in report.scopes}
    assert "memory" in named
    assert named["memory"].bytes == 0
    assert named["tasks"].files == 0


def test_single_file_in_memory_scope(tmp_path: Path):
    sac = tmp_path / ".sac"
    mem_dir = sac / "memory"
    mem_dir.mkdir(parents=True)
    content = b"hello world"
    (mem_dir / "project.md").write_bytes(content)
    report = compute_sac_size(tmp_path)
    assert report.total_bytes == len(content)
    assert report.total_files == 1
    named = {e.name: e for e in report.scopes}
    assert named["memory"].bytes == len(content)
    assert named["memory"].files == 1
    # Other named scopes are zero
    assert named["tasks"].bytes == 0
    assert named["checkpoints"].bytes == 0


def test_mixed_scopes(tmp_path: Path):
    sac = tmp_path / ".sac"
    (sac / "memory").mkdir(parents=True)
    (sac / "memory" / "notes.md").write_bytes(b"abc")
    (sac / "tasks").mkdir(parents=True)
    (sac / "tasks" / "foo.json").write_bytes(b"12345")
    (sac / "audit").mkdir(parents=True)
    (sac / "audit" / "log.jsonl").write_bytes(b"x" * 10)
    report = compute_sac_size(tmp_path)
    assert report.total_bytes == 3 + 5 + 10
    assert report.total_files == 3
    named = {e.name: e for e in report.scopes}
    assert named["memory"].bytes == 3
    assert named["tasks"].bytes == 5
    assert named["audit"].bytes == 10
    assert named["other"].bytes == 0


def test_file_outside_named_scopes_goes_to_other(tmp_path: Path):
    sac = tmp_path / ".sac"
    extra = sac / "extra"
    extra.mkdir(parents=True)
    (extra / "foo.bin").write_bytes(b"data!")
    report = compute_sac_size(tmp_path)
    named = {e.name: e for e in report.scopes}
    assert named["other"].bytes == 5
    assert named["other"].files == 1


def test_symlink_skipped(tmp_path: Path):
    sac = tmp_path / ".sac"
    mem_dir = sac / "memory"
    mem_dir.mkdir(parents=True)
    real_file = tmp_path / "real.txt"
    real_file.write_bytes(b"real content")
    link = mem_dir / "linked.txt"
    link.symlink_to(real_file)
    report = compute_sac_size(tmp_path)
    assert report.total_bytes == 0
    assert report.total_files == 0


def test_temp_file_skipped(tmp_path: Path):
    sac = tmp_path / ".sac"
    tasks_dir = sac / "tasks"
    tasks_dir.mkdir(parents=True)
    real = tasks_dir / "my-task.json"
    real.write_bytes(b"real")
    tmp_file = tasks_dir / ".my-task.json.abcdef01234567890123456789012345.tmp"
    tmp_file.write_bytes(b"temp content should be skipped")
    report = compute_sac_size(tmp_path)
    assert report.total_bytes == 4
    assert report.total_files == 1


def test_budgets_counted_under_tasks(tmp_path: Path):
    sac = tmp_path / ".sac"
    budgets = sac / "tasks" / "budgets"
    budgets.mkdir(parents=True)
    (budgets / "task-abc.json").write_bytes(b"budget data")
    report = compute_sac_size(tmp_path)
    named = {e.name: e for e in report.scopes}
    assert named["tasks"].files == 1
    assert named["tasks"].bytes == 11


def test_scopes_sorted_by_name(tmp_path: Path):
    sac = tmp_path / ".sac"
    sac.mkdir()
    report = compute_sac_size(tmp_path)
    names = [e.name for e in report.scopes]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_cli_size_missing_sac(tmp_path: Path, monkeypatch):
    result = _invoke(tmp_path, monkeypatch, "size", "--json")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"
    assert data["data"]["exists"] is False
    assert data["data"]["total_bytes"] == 0


def test_cli_size_json_envelope(tmp_path: Path, monkeypatch):
    sac = tmp_path / ".sac"
    sac.mkdir()
    result = _invoke(tmp_path, monkeypatch, "size", "--json")
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["command"] == "memory size"
    assert parsed["status"] == "success"
    assert "data" in parsed
    assert parsed["data"]["experimental"] is True


def test_cli_size_human_output_no_crash(tmp_path: Path, monkeypatch):
    sac = tmp_path / ".sac"
    (sac / "memory").mkdir(parents=True)
    (sac / "memory" / "notes.md").write_bytes(b"hello")
    result = _invoke(tmp_path, monkeypatch, "size")
    assert result.exit_code == 0
    assert "Size Breakdown" in result.stdout or "Scope" in result.stdout
