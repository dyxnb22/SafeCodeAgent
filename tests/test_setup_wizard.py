import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.setup import write_setup


def test_write_setup_creates_config_and_env(tmp_path):
    result = write_setup(
        tmp_path,
        provider="mock",
        model="demo-model",
        policy="strict",
        approval_dir=tmp_path.parent / "approvals",
        sandbox_approval_dir=tmp_path.parent / "sandbox-approvals",
    )

    assert result.config_path.exists()
    assert result.env_path.exists()
    assert 'provider = "mock"' in result.config_path.read_text(encoding="utf-8")
    assert 'model = "demo-model"' in result.config_path.read_text(encoding="utf-8")
    assert 'policy = "strict"' in result.config_path.read_text(encoding="utf-8")
    assert "SAFECODE_APPROVAL_DIR" in result.env_path.read_text(encoding="utf-8")


def test_write_setup_rejects_invalid_policy(tmp_path):
    with pytest.raises(ValueError, match="policy"):
        write_setup(tmp_path, policy="reckless")


def test_write_setup_refuses_to_overwrite_without_force(tmp_path):
    write_setup(
        tmp_path,
        approval_dir=tmp_path.parent / "approvals",
        sandbox_approval_dir=tmp_path.parent / "sandbox-approvals",
    )
    with pytest.raises(FileExistsError):
        write_setup(
            tmp_path,
            approval_dir=tmp_path.parent / "approvals",
            sandbox_approval_dir=tmp_path.parent / "sandbox-approvals",
        )


def test_setup_cli_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "setup",
            "--yes",
            "--provider",
            "mock",
            "--model",
            "demo",
            "--policy",
            "learning",
            "--approval-dir",
            str(tmp_path.parent / "approvals"),
            "--sandbox-approval-dir",
            str(tmp_path.parent / "sandbox-approvals"),
        ],
    )

    assert result.exit_code == 0
    assert "SafeCode Setup" in result.output
    assert (tmp_path / ".sac" / "config.toml").exists()
    assert (tmp_path / ".sac" / "setup.env").exists()


def test_setup_cli_rejects_second_run_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = [
        "setup",
        "--yes",
        "--approval-dir",
        str(tmp_path.parent / "approvals"),
        "--sandbox-approval-dir",
        str(tmp_path.parent / "sandbox-approvals"),
    ]
    assert CliRunner().invoke(app, args).exit_code == 0
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0
    assert "already exist" in result.output
