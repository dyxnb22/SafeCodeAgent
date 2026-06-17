"""Tests for sac test-gen."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_testgen import _build_test_prompt
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


def test_build_test_prompt_for_file_symbol(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def parse_config(x):\n    return x\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_existing.py").write_text("def test_other(): pass\n", encoding="utf-8")

    prompt, metadata = _build_test_prompt(tmp_path, "src/foo.py::parse_config", None)

    assert "parse_config" in prompt
    assert "at least three" in prompt
    assert metadata["suggested_output"] == "tests/test_foo.py"


def test_testgen_cli_outputs_pending_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("def compute(x):\n    return x * 2\n", encoding="utf-8")
    proposal = PatchProposal(
        id="testgen-1",
        task="tests",
        blocks=[
            PatchBlock(
                operation="create",
                file_path=Path("tests/test_foo.py"),
                content="def test_compute(): assert True\n",
            )
        ],
        created_at=utc_now_iso(),
        model="mock",
    )

    fake_result = SimpleNamespace(
        proposal=proposal,
        pending_patch_path=tmp_path / ".sac" / "pending_patch.json",
    )

    with patch("safecode.agent.orchestrator.AgentOrchestrator.edit", return_value=fake_result) as edit:
        result = CliRunner().invoke(app, ["test-gen", "generate", "foo.py", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "pending"
    assert payload["data"]["files"] == ["tests/test_foo.py"]
    assert edit.called
