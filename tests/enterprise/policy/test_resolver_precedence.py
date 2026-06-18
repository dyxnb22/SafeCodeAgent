"""Policy resolver precedence tests."""

from pathlib import Path

import yaml

from safecode.enterprise.policy.models import PolicyLayer, PolicyValue
from safecode.enterprise.policy.resolver import PolicyResolver, resolve_policy


def _write_policy(path: Path, policies: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"version": 1, "policies": policies}), encoding="utf-8")


def test_org_only_snapshot_reflects_org_keys(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"github_read": "AUTO", "file_write": "GATE"})
    snapshot = resolve_policy(tmp_path, config_root=config_root)
    assert snapshot.merged["github_read"].value == "AUTO"
    assert snapshot.merged["file_write"].value == "GATE"
    assert snapshot.snapshot_id.startswith("snapshot-")


def test_higher_layer_wins_over_lower(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"command_execute": "GATE"})
    _write_policy(config_root / "user.yaml", {"command_execute": "CONFIRM"})
    project_path = tmp_path / ".sac" / "enterprise" / "project.yaml"
    _write_policy(project_path, {"command_execute": "AUTO"})
    snapshot = resolve_policy(tmp_path, config_root=config_root)
    assert snapshot.merged["command_execute"].value == "GATE"


def test_layer_order_is_workflow_env_project_user_org(tmp_path: Path):
    resolver = PolicyResolver(
        repo_root=tmp_path,
        workflow_overrides={"scanner_run": "AUTO"},
        extra_layers=[
            PolicyLayer(
                name="env",
                source_ref="test-env",
                values={"scanner_run": PolicyValue(key="scanner_run", value="CONFIRM")},
            )
        ],
    )
    snapshot = resolver.resolve()
    names = [layer.name for layer in snapshot.layers]
    assert names.index("workflow") < names.index("env")
    assert names.index("env") < names.index("project")
    assert names.index("project") < names.index("user")
    assert names.index("user") < names.index("org")


def test_env_layer_overrides_workflow(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAC_ENTERPRISE_SCANNER_RUN", "GATE")
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"github_read": "AUTO"})
    snapshot = resolve_policy(
        tmp_path,
        config_root=config_root,
        workflow_overrides={"scanner_run": "AUTO"},
    )
    assert snapshot.merged["scanner_run"].value == "GATE"
