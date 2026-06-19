from __future__ import annotations

import hashlib
import os
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.demo.agent_loop_demo import EXPECTED_TRANSCRIPT, run_agent_loop_demo

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "fastapi-todo"
EXPECTED = EXAMPLE / "demo" / "expected-transcript.md"
RUN_DEMO = EXAMPLE / "demo" / "run-demo.sh"


def _source_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(EXAMPLE.rglob("*")):
        if path.is_file() and ".pytest_cache" not in path.parts and "__pycache__" not in path.parts:
            digest.update(path.relative_to(EXAMPLE).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_sac_demo_agent_loop_runs_on_mock_provider() -> None:
    result = CliRunner().invoke(app, ["demo", "agent-loop"])

    assert result.exit_code == 0, result.output
    assert "[setup] provider=mock network=disabled" in result.output
    assert "[task] add a DELETE /todos/{id} endpoint with a passing test" in result.output


def test_temp_working_copy_is_used_and_cleaned_up() -> None:
    result = run_agent_loop_demo(ROOT)

    assert result.source_root == EXAMPLE
    assert result.working_copy.parent == result.temp_parent
    assert result.cleanup_done is True
    assert not result.temp_parent.exists()
    assert not result.working_copy.exists()


def test_output_matches_expected_transcript() -> None:
    assert EXPECTED.read_text(encoding="utf-8").strip() == EXPECTED_TRANSCRIPT.strip()

    result = CliRunner().invoke(app, ["demo", "agent-loop"])

    assert result.exit_code == 0, result.output
    assert result.output.strip() == EXPECTED_TRANSCRIPT.strip()


def test_no_live_provider_or_network_path_is_used(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "should-not-be-read")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-read")

    result = run_agent_loop_demo(ROOT)

    assert "provider=mock" in result.transcript
    assert "network=disabled" in result.transcript


def test_demo_does_not_mutate_source_example() -> None:
    before = _source_digest()

    run_agent_loop_demo(ROOT)

    assert _source_digest() == before


def test_run_demo_script_is_executable_and_uses_documented_sac_command() -> None:
    assert os.access(RUN_DEMO, os.X_OK)
    text = RUN_DEMO.read_text(encoding="utf-8")

    assert "sac demo agent-loop" in text
    assert "mktemp -d" in text
    assert "cp -R" in text
    assert "git push" not in text
    assert "DEEPSEEK_API_KEY" not in text


def test_demo_agent_loop_remains_experimental() -> None:
    help_result = CliRunner().invoke(app, ["--help"])
    command_help = CliRunner().invoke(app, ["demo", "agent-loop", "--help"])

    assert help_result.exit_code == 0
    assert " demo " in help_result.output
    assert command_help.exit_code == 0
    assert "EXPERIMENTAL" in command_help.output
