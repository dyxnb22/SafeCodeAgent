"""Tests for v4.14.1 provider status top-line verdict."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


class TestProviderStatusVerdict:
    def test_status_shows_broken_when_no_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["provider", "status"], catch_exceptions=False)
        assert "Verdict:" in result.stdout
        assert "BROKEN" in result.stdout

    def test_status_shows_details_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["provider", "status"], catch_exceptions=False)
        assert "Details:" in result.stdout

    def test_status_shows_ready_with_configured_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        user_config = tmp_path / ".safecode" / "config.toml"
        user_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.write_text(
            '[providers]\nactive = "deepseek"\n'
            '\n[providers.deepseek]\nbase_url = "https://api.deepseek.com/v1"\n'
            'api_key = "sk-test-key"\ndefault_model = "deepseek-v4-flash"\n'
            "model_aliases = {flash = \"deepseek-v4-flash\", pro = \"deepseek-v4-pro\"}\n"
            'network_allowlist = ["api.deepseek.com"]\n'
            '\n[sandbox]\nnetwork_enabled = true\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\nbase_url = "https://api.deepseek.com/v1"\n'
            "[sandbox]\nnetwork_enabled = true\nnetwork_allowlist = [\"api.deepseek.com\"]\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["provider", "status"], catch_exceptions=False)
        assert "Verdict:" in result.stdout
        assert "READY" in result.stdout
        assert "Details:" in result.stdout

    def test_verdict_line_does_not_contain_experimental(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\nbase_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["provider", "status"], catch_exceptions=False)
        # The EXPERIMENTAL tag belongs in the header line, not in the verdict text
        lines_before_details = result.stdout.split("Details:")[0]
        verdict_line = [l for l in lines_before_details.split("\n") if "Verdict:" in l]
        assert len(verdict_line) == 1
        assert "EXPERIMENTAL" not in verdict_line[0]


class TestQuickstartProviderNotReady:
    def test_quickstart_shows_provider_not_ready_with_mock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["quickstart", "--yes"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Provider not ready" in result.stdout
        assert "sac doctor" in result.stdout

    def test_quickstart_demo_flag_still_works_with_mock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        demo_dest = tmp_path / "demo-out"
        result = runner.invoke(
            app,
            ["quickstart", "--yes", "--demo", "--demo-dest", str(demo_dest)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Provider not ready" in result.stdout
        assert "Demo project created" in result.stdout
        assert demo_dest.exists()
