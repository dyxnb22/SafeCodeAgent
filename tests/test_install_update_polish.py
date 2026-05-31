from typer.testing import CliRunner

from safecode import __version__
from safecode.cli import app
from safecode.doctor import Doctor


def test_package_version_is_current():
    assert __version__ == "2.3.4"


def test_doctor_reports_config_and_approval_env(tmp_path, monkeypatch):
    approval_dir = tmp_path.parent / "approvals"
    sandbox_dir = tmp_path.parent / "sandbox-approvals"
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(approval_dir))
    monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(sandbox_dir))
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text("policy = \"normal\"\n", encoding="utf-8")

    checks = {check.name: check for check in Doctor(tmp_path).run()}

    assert checks["config"].passed is True
    assert checks["sac_dir"].passed is True
    assert checks["approval_dir"].detail == str(approval_dir)
    assert checks["sandbox_approval_dir"].detail == str(sandbox_dir)


def test_version_cli_runs():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "2.3.4" in result.output
    assert "git pull" in result.output


def test_doctor_cli_mentions_new_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "approval_dir" in result.output
    assert "sandbox_approval_dir" in result.output
