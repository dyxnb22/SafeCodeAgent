"""Tests for sac mcp doctor command (v3.8.1 T-3.8.1-B).

Covers:
- Reports binary path, scope, stdio configured, last call status, lifecycle PID
- --json output format
- No subprocess is launched (pure read)
- Missing server name gives error exit
- No servers configured: empty result, not error
- Last call status sourced from audit log
- Lifecycle PID sourced from PID file; running vs dead label
- All-servers mode (no server argument)
"""

from __future__ import annotations

import json
import os


def _write_server_toml(tmp_path, server_name: str = "myserver", scope: str = "read_only") -> None:
    sac = tmp_path / ".sac"
    sac.mkdir(exist_ok=True)
    (sac / "mcp.toml").write_text(
        f'[servers.{server_name}]\ncommand = "echo"\nscope = "{scope}"\n',
        encoding="utf-8",
    )


def _invoke_doctor(tmp_path, args: list, catch_exit: bool = True):
    """Invoke mcp_doctor via typer test client."""
    from typer.testing import CliRunner
    from safecode.cli_mcp import mcp_app

    runner = CliRunner()
    result = runner.invoke(mcp_app, ["doctor"] + args, catch_exceptions=False)
    return result


class TestMCPDoctorNoServers:
    def test_no_servers_exits_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _invoke_doctor(tmp_path, [])
        assert result.exit_code == 0

    def test_no_servers_json_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _invoke_doctor(tmp_path, ["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["servers"] == []


class TestMCPDoctorServerNotFound:
    def test_unknown_server_exits_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["no_such_server"])
        assert result.exit_code == 1

    def test_unknown_server_json_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["no_such_server", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "no_such_server" in data.get("error", "")


class TestMCPDoctorReportFields:
    def test_reports_server_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path, "myserver", "read_only")
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        server_info = data["data"]["servers"][0]
        assert server_info["server"] == "myserver"

    def test_reports_scope(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path, "myserver", "denied")
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["servers"][0]["scope"] == "denied"

    def test_reports_enabled(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["servers"][0]["enabled"] is True

    def test_reports_binary(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        server_info = data["data"]["servers"][0]
        assert "binary" in server_info

    def test_reports_stdio_configured_false_when_no_argv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["servers"][0]["stdio_configured"] is False

    def test_reports_stdio_configured_true_when_argv_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sac = tmp_path / ".sac"
        sac.mkdir(exist_ok=True)
        (sac / "mcp.toml").write_text(
            '[servers.myserver]\ncommand = "echo"\nscope = "read_only"\nargv = ["echo", "hi"]\n',
            encoding="utf-8",
        )
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["servers"][0]["stdio_configured"] is True

    def test_reports_lifecycle_pid_none_when_no_pid_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["servers"][0]["lifecycle_pid"] is None

    def test_reports_lifecycle_pid_when_pid_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        pid_dir = tmp_path / ".sac" / "mcp"
        pid_dir.mkdir(parents=True, exist_ok=True)
        # Use own PID so is_running check passes.
        (pid_dir / "myserver.pid").write_text(str(os.getpid()), encoding="utf-8")
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["servers"][0]["lifecycle_pid"] == os.getpid()
        assert data["data"]["servers"][0]["lifecycle_running"] is True

    def test_experimental_flag_in_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        assert data["data"]["experimental"] is True

    def test_last_call_fields_none_when_no_audit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        info = data["data"]["servers"][0]
        assert info["last_call_type"] is None
        assert info["last_call_status"] is None
        assert info["last_call_timestamp"] is None


class TestMCPDoctorLastCallFromAudit:
    def _write_audit_event(self, tmp_path, server_name: str, event_type: str, status: str) -> None:
        import json as _json
        from safecode.audit.logger import AuditLogger
        from safecode.audit.models import AuditEvent
        from safecode.utils.time import utc_now_iso

        logger = AuditLogger(tmp_path)
        logger.write(AuditEvent(
            type=event_type,
            timestamp=utc_now_iso(),
            status=status,
            message=f"test event for {server_name}",
            metadata={"server": server_name},
        ))

    def test_last_call_status_from_audit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        self._write_audit_event(tmp_path, "myserver", "mcp_call_completed", "success")
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        info = data["data"]["servers"][0]
        assert info["last_call_type"] == "mcp_call_completed"
        assert info["last_call_status"] == "success"
        assert info["last_call_timestamp"] is not None

    def test_last_call_ignores_other_server_events(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        self._write_audit_event(tmp_path, "other_server", "mcp_call_completed", "success")
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        data = json.loads(result.output)
        info = data["data"]["servers"][0]
        assert info["last_call_type"] is None


class TestMCPDoctorAllServers:
    def test_all_servers_returned_when_no_filter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sac = tmp_path / ".sac"
        sac.mkdir(exist_ok=True)
        (sac / "mcp.toml").write_text(
            '[servers.alpha]\ncommand = "echo"\n[servers.beta]\ncommand = "cat"\n',
            encoding="utf-8",
        )
        result = _invoke_doctor(tmp_path, ["--json"])
        data = json.loads(result.output)
        names = [s["server"] for s in data["data"]["servers"]]
        assert "alpha" in names
        assert "beta" in names

    def test_single_server_filter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sac = tmp_path / ".sac"
        sac.mkdir(exist_ok=True)
        (sac / "mcp.toml").write_text(
            '[servers.alpha]\ncommand = "echo"\n[servers.beta]\ncommand = "cat"\n',
            encoding="utf-8",
        )
        result = _invoke_doctor(tmp_path, ["alpha", "--json"])
        data = json.loads(result.output)
        assert len(data["data"]["servers"]) == 1
        assert data["data"]["servers"][0]["server"] == "alpha"


class TestMCPDoctorNoPureRead:
    def test_doctor_does_not_spawn_subprocess(self, tmp_path, monkeypatch):
        """Verify no subprocess is launched; relies on mcp.toml with echo as command."""
        import subprocess as sp

        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        original_popen = sp.Popen
        spawned: list[bool] = []

        def mock_popen(*a, **kw):
            spawned.append(True)
            return original_popen(*a, **kw)

        monkeypatch.setattr(sp, "Popen", mock_popen)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        assert result.exit_code == 0
        assert not spawned, "doctor must not spawn subprocesses"

    def test_doctor_does_not_run_subprocess(self, tmp_path, monkeypatch):
        import subprocess as sp

        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        original_run = sp.run
        ran: list[bool] = []

        def mock_run(*a, **kw):
            ran.append(True)
            return original_run(*a, **kw)

        monkeypatch.setattr(sp, "run", mock_run)
        result = _invoke_doctor(tmp_path, ["myserver", "--json"])
        assert result.exit_code == 0
        assert not ran, "doctor must not call subprocess.run"


class TestMCPDoctorHumanOutput:
    def test_human_output_contains_server_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path, "myserver")
        result = _invoke_doctor(tmp_path, ["myserver"])
        assert "myserver" in result.output

    def test_human_output_contains_scope(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path, "myserver", "denied")
        result = _invoke_doctor(tmp_path, ["myserver"])
        assert "denied" in result.output

    def test_human_output_contains_experimental_label(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_server_toml(tmp_path)
        result = _invoke_doctor(tmp_path, ["myserver"])
        assert "EXPERIMENTAL" in result.output
