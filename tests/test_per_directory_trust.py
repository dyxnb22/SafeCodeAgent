"""Tests for v3.11.0 per-directory trust."""

from __future__ import annotations

from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig, TrustRoot, effective_trust_for_path, merge_trusted_config


def test_user_level_trust_root_applies_to_subdirectory(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "user.toml"
    trusted = tmp_path / "repo" / "src"
    child = trusted / "pkg"
    child.mkdir(parents=True)
    user_config.write_text(
        f'policy = "balanced"\n\n[[trust.roots]]\npath = "{trusted}"\npolicy = "strict"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))

    result = effective_trust_for_path(tmp_path / "repo", child)

    assert result["trusted"] is True
    assert result["effective_policy"] == "strict"
    assert result["matched_roots"] == [str(trusted)]


def test_project_local_trust_does_not_widen_user_safety(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / ".sac").mkdir(parents=True)
    (repo / ".sac" / "config.toml").write_text(
        'policy = "experimental"\n\n[[trust.roots]]\npath = "."\npolicy = "experimental"\n',
        encoding="utf-8",
    )
    user_config = tmp_path / "user.toml"
    user_config.write_text('policy = "strict"\n', encoding="utf-8")
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))

    result = effective_trust_for_path(repo, repo)

    assert result["trusted"] is False
    assert result["effective_policy"] == "strict"
    assert result["project_trust_blocked"] is True
    events = AuditLogger(repo).read_recent(limit=5)
    assert any(event.type == "trust_config_lookup" and event.status == "blocked" for event in events)


def test_merge_trusted_config_keeps_user_trust_only(tmp_path) -> None:
    user = SafeCodeConfig()
    project = SafeCodeConfig()
    user.trust.roots.append(TrustRoot(path=str(tmp_path / "trusted"), policy="strict"))
    project.trust.roots.append(TrustRoot(path=str(tmp_path), policy="experimental"))

    merged = merge_trusted_config(user, project)

    assert len(merged.trust.roots) == 1
    assert merged.trust.roots[0].policy == "strict"


def test_every_trust_lookup_is_audited(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path / "anchors"))

    effective_trust_for_path(repo, repo)

    events = AuditLogger(repo).read_recent(limit=5)
    assert any(event.type == "trust_config_lookup" for event in events)
