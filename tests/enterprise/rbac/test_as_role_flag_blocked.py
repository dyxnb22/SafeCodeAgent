"""--as-role policy gate tests."""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.rbac.models import Role, resolve_subject


def _write_policy(path: Path, policies: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"version": 1, "policies": policies}), encoding="utf-8")


def test_as_role_blocked_without_org_flag(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"allow_as_role_flag": False})
    with pytest.raises(PermissionError, match="allow_as_role_flag"):
        resolve_subject("user:test", config_root=config_root, as_role="platform_admin")


def test_as_role_allowed_when_org_flag_true(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"allow_as_role_flag": True})
    subject = resolve_subject("user:test", config_root=config_root, as_role="platform_admin")
    assert subject.roles == (Role.platform_admin,)


def test_cli_workflow_run_rejects_as_role_without_policy(tmp_path: Path):
    config_root = tmp_path / "config"
    _write_policy(config_root / "org.yaml", {"allow_as_role_flag": False})
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "run",
            "--task",
            "pr_review",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
            "--config-root",
            str(config_root),
            "--as-role",
            "maintainer",
        ],
        env={"WORKFLOW_RUNTIME": "local"},
    )
    assert result.exit_code == 1
    error_output = result.output
    if result.stderr_bytes is not None:
        error_output += result.stderr
    assert "allow_as_role_flag" in error_output
