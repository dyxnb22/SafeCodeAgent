"""Tests for v3.11.1 policy diff."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from safecode.cli import app
from safecode.policy.audit import diff_policy, render_policy_diff


def test_policy_diff_entries_are_deterministic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "missing-user.toml"))
    first = diff_policy(tmp_path, "balanced").to_dict()
    second = diff_policy(tmp_path, "balanced").to_dict()

    assert first == second
    assert [entry["knob"] for entry in first["entries"]] == sorted(entry["knob"] for entry in first["entries"])


def test_policy_diff_reports_knob_delta(tmp_path, monkeypatch) -> None:
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text('policy = "strict"\n', encoding="utf-8")
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "missing-user.toml"))

    result = diff_policy(tmp_path, "experimental")

    assert result.has_differences is True
    assert any(entry.knob == "shell.allowed_commands" and not entry.matches for entry in result.entries)


def test_policy_diff_render_is_redacted_and_stable(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "user.toml"
    user_config.write_text(
        '[llm]\nbase_url = "https://example.invalid/SECRET_TOKEN"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))

    text = render_policy_diff(diff_policy(tmp_path, "balanced"))

    assert "SECRET_TOKEN" not in text
    assert "shell.block_high_risk" in text
    assert "sandbox.network_enabled" in text


def test_policy_diff_cli_json_uses_envelope(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "missing-user.toml"))

    result = CliRunner().invoke(app, ["config", "diff", "--against", "balanced", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "config diff"
    assert payload["status"] == "success"
    assert payload["data"]["against"] == "balanced"
    assert "error" not in payload


def test_policy_diff_cli_unknown_preset_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["config", "diff", "--against", "reckless", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert "reckless" in payload["error"]
