"""Tests for v3.11.0 ephemeral trust grants."""

from __future__ import annotations

from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.cli import app
from safecode.config import clear_ephemeral_trust, effective_trust_for_path, grant_ephemeral_trust, revoke_ephemeral_trust


def test_ephemeral_trust_is_in_memory_only(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
    clear_ephemeral_trust()

    grant_id = grant_ephemeral_trust(repo, policy="strict")
    result = effective_trust_for_path(repo, repo)

    assert result["trusted"] is True
    assert result["ephemeral_count"] == 1
    assert not (repo / ".sac" / "config.toml").exists()
    assert not list(repo.rglob("*trust*"))
    assert revoke_ephemeral_trust(grant_id) is True


def test_ephemeral_trust_expires_when_session_memory_clears(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))
    clear_ephemeral_trust()
    grant_ephemeral_trust(repo, policy="strict")

    clear_ephemeral_trust()
    result = effective_trust_for_path(repo, repo)

    assert result["trusted"] is False
    assert result["ephemeral_count"] == 0


def test_trust_grant_cli_requires_ephemeral_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path.parent / "anchors-require-flag"))
    result = CliRunner().invoke(app, ["trust", "grant", "."])

    assert result.exit_code == 1
    assert "--until-end-of-session" in result.output


def test_trust_grant_cli_audits_and_does_not_persist(tmp_path, monkeypatch) -> None:
    clear_ephemeral_trust()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path.parent / "anchors-cli-grant"))

    result = CliRunner().invoke(app, ["trust", "grant", ".", "--until-end-of-session"])

    assert result.exit_code == 0
    assert not (tmp_path / ".sac" / "config.toml").exists()
    events = AuditLogger(tmp_path).read_recent(limit=5)
    assert any(event.type == "ephemeral_trust_granted" for event in events)
    assert all(event.metadata.get("persisted") != "true" for event in events)
