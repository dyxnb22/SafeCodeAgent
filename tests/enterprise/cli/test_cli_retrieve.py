"""CLI tests for sac enterprise retrieve (v1.1.3-T4)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app

_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _ROOT / "examples/enterprise/knowledge_sources.yaml"


def test_cli_retrieve_prints_json_citations():
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "retrieve",
            "--manifest",
            str(_MANIFEST),
            "--root",
            str(_ROOT),
            "--actor-scope",
            "org,appsec",
            "sql injection parameterized",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert payload
    assert payload[0]["source_id"]


def test_cli_retrieve_exit_code_two_when_no_results():
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "retrieve",
            "--manifest",
            str(_MANIFEST),
            "--root",
            str(_ROOT),
            "--actor-scope",
            "missing-scope",
            "content",
        ],
    )
    assert result.exit_code == 2
