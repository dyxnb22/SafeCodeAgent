"""Tests for v2.6.19 policy audit command."""

from typer.testing import CliRunner

from safecode.cli import app
from safecode.policy.audit import audit_policy, render_policy_audit


def test_policy_audit_passes_with_no_project_config(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAFECODE_POLICY", raising=False)
    result = audit_policy(tmp_path)
    assert result.ok is True
    assert {"strict", "balanced", "experimental", "normal", "learning"} <= set(result.known_names)


def test_policy_audit_accepts_legacy_aliases(tmp_path) -> None:
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text('policy = "learning"\n', encoding="utf-8")
    result = audit_policy(tmp_path)
    assert result.ok is True
    assert result.project_policy == "learning"
    assert result.aliases_ok is True


def test_policy_audit_reports_unknown_project_policy(tmp_path) -> None:
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text('policy = "reckless"\n', encoding="utf-8")
    result = audit_policy(tmp_path)
    assert result.ok is False
    assert any("reckless" in issue for issue in result.issues)


def test_policy_audit_reports_unknown_env_policy(tmp_path) -> None:
    result = audit_policy(tmp_path, env_policy="future_policy")
    assert result.ok is False
    assert any("SAFECODE_POLICY" in issue for issue in result.issues)


def test_render_policy_audit_includes_next_steps(tmp_path) -> None:
    result = audit_policy(tmp_path, env_policy="future_policy")
    text = render_policy_audit(result)
    assert "Status: FAIL" in text
    assert "Next steps:" in text


def test_policy_audit_cli_success(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SAFECODE_POLICY", raising=False)
    result = CliRunner().invoke(app, ["config", "policy-audit"])
    assert result.exit_code == 0
    assert "Policy audit passed" in result.output


def test_policy_audit_cli_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_POLICY", "future_policy")
    result = CliRunner().invoke(app, ["config", "policy-audit"])
    assert result.exit_code == 1
    assert "future_policy" in result.output
