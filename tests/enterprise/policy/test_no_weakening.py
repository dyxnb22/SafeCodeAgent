"""Policy no-weakening tests."""

from pathlib import Path

import yaml

from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.policy.resolver import resolve_policy


def _write_policy(path: Path, policies: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"version": 1, "policies": policies}), encoding="utf-8")


def test_project_cannot_weaken_github_write_from_gate_to_auto(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"github_write_comment": "GATE"})
    project_path = tmp_path / ".sac" / "enterprise" / "project.yaml"
    _write_policy(project_path, {"github_write": "AUTO"})
    snapshot = resolve_policy(tmp_path, config_root=config_root)
    assert snapshot.merged["github_write_comment"].value == "GATE"
    blocked = snapshot.blocked_overrides
    assert len(blocked) == 1
    assert blocked[0].key == "github_write_comment"
    assert blocked[0].attempted_value == "AUTO"
    assert blocked[0].final_value == "GATE"
    assert blocked[0].layer == "project"


def test_project_override_blocked_audit_event(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"github_write_comment": "GATE"})
    project_path = tmp_path / ".sac" / "enterprise" / "project.yaml"
    _write_policy(project_path, {"github_write": "AUTO"})
    snapshot = resolve_policy(tmp_path, config_root=config_root)
    audit = EnterpriseAuditChain(tmp_path)
    for item in snapshot.blocked_overrides:
        audit.emit(
            AuditEventKind.project_override_blocked,
            run_id="run-policy-test",
            actor_id="user:test",
            payload={
                "key": item.key,
                "attempted_value": item.attempted_value,
                "final_value": item.final_value,
                "layer": item.layer,
            },
        )
    events = audit.iter_events()
    assert any(event.type == "policy.project_override_blocked" for event in events)
