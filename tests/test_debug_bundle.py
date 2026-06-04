"""Tests for experimental sac debug bundle."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.cli import app
from safecode.debug.bundle import MAX_BUNDLE_BYTES, create_debug_bundle
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.facade import MemoryFacade
from safecode.task.store import TaskStore

runner = CliRunner()


def _members(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, "r:gz") as tar:
        return {member.name: tar.extractfile(member).read() for member in tar.getmembers() if member.isfile()}


def test_bundle_manifest_and_round_trip(tmp_path) -> None:
    out = tmp_path / "bundle.tar.gz"
    result = create_debug_bundle(tmp_path, out_path=out)
    assert result.path == out
    members = _members(out)
    assert "manifest.json" in members
    manifest = json.loads(members["manifest.json"])
    assert manifest["schema"] == "safecode-debug-bundle-v1"
    assert manifest["excludes_project_source"] is True


def test_bundle_redacts_secret_token_key_substrings(tmp_path) -> None:
    RuntimeLogger(tmp_path).write(
        "error",
        "test",
        "api_key=abc123 token=def456 secret=ghi789",
        failure_category="unknown",
    )
    out = tmp_path / "bundle.tar.gz"
    create_debug_bundle(tmp_path, out_path=out)
    combined = b"\n".join(_members(out).values()).decode("utf-8").lower()
    assert "abc123" not in combined
    assert "def456" not in combined
    assert "ghi789" not in combined
    assert "api_key" not in combined
    assert "token" not in combined
    assert "secret" not in combined


def test_bundle_does_not_include_project_source(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('source')\n", encoding="utf-8")
    out = tmp_path / "bundle.tar.gz"
    create_debug_bundle(tmp_path, out_path=out)
    members = _members(out)
    assert "app.py" not in members
    assert all(not name.endswith(".py") for name in members)
    assert "print('source')" not in b"\n".join(members.values()).decode("utf-8")


def test_bundle_refuses_overwrite_unless_force(tmp_path) -> None:
    out = tmp_path / "bundle.tar.gz"
    create_debug_bundle(tmp_path, out_path=out)
    with pytest.raises(FileExistsError):
        create_debug_bundle(tmp_path, out_path=out)
    create_debug_bundle(tmp_path, out_path=out, force=True)


def test_bundle_task_selection(tmp_path) -> None:
    store = TaskStore(tmp_path)
    first = store.create("first task")
    second = store.create("second task")
    out = tmp_path / "bundle.tar.gz"
    create_debug_bundle(tmp_path, task_id=first.task_id, out_path=out)
    sidecars = json.loads(_members(out)["task_sidecars.json"])
    assert [task["task_id"] for task in sidecars] == [first.task_id]
    assert second.task_id not in json.dumps(sidecars)


def test_bundle_refuses_audit_integrity_failure(tmp_path) -> None:
    logger = AuditLogger(tmp_path)
    logger.write(AuditEvent(type="test", timestamp="2026-01-01T00:00:00+00:00", message="ok"))
    log = tmp_path / ".sac" / "logs" / "events.jsonl"
    log.write_text(log.read_text(encoding="utf-8").replace("ok", "tampered"), encoding="utf-8")
    with pytest.raises(ValueError, match="Audit integrity"):
        create_debug_bundle(tmp_path, out_path=tmp_path / "bundle.tar.gz")


def test_cli_bundle_json_and_force(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "bundle.tar.gz"
    first = runner.invoke(app, ["debug", "bundle", "--out", str(out), "--json"], catch_exceptions=False)
    assert first.exit_code == 0
    data = json.loads(first.output)
    assert data["command"] == "debug bundle"
    assert data["data"]["size_bytes"] <= MAX_BUNDLE_BYTES
    second = runner.invoke(app, ["debug", "bundle", "--out", str(out), "--json"], catch_exceptions=False)
    assert second.exit_code == 0
    assert json.loads(second.output)["status"] == "error"
    forced = runner.invoke(app, ["debug", "bundle", "--out", str(out), "--force", "--json"], catch_exceptions=False)
    assert forced.exit_code == 0


def test_bundle_includes_memory_metadata_only(tmp_path) -> None:
    MemoryFacade(tmp_path).add_note("project note without sensitive words")
    out = tmp_path / "bundle.tar.gz"
    create_debug_bundle(tmp_path, out_path=out)
    members = _members(out)
    metadata = json.loads(members["memory_metadata.json"])
    assert metadata["project_notes"]["exists"] is True
    assert "project note without sensitive words" not in b"\n".join(members.values()).decode("utf-8")
