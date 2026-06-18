"""Tests for v2.6.16 release checklist upgrade."""

from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.checklist import render_release_checklist


def test_checklist_normalizes_version_prefix() -> None:
    text = render_release_checklist("2.6.16")
    assert "# SafeCode Release Checklist v2.6.16" in text


def test_checklist_includes_bump_flow() -> None:
    text = render_release_checklist("v2.6.16")
    assert "sac release bump 2.6.16" in text


def test_checklist_includes_release_gates() -> None:
    text = render_release_checklist("v2.6.16")
    assert "release check" in text
    assert "release smoke" in text
    assert "release meta" in text
    assert "release preflight" in text


def test_checklist_includes_commit_tag_and_exact_tag() -> None:
    text = render_release_checklist("v2.6.16")
    assert 'git commit -m "Implement v2.6.16 <summary>"' in text
    assert 'git tag -a v2.6.16 -m "v2.6.16 <summary>"' in text
    assert "git describe --exact-match --tags HEAD" in text


def test_cli_checklist_renders_upgraded_flow() -> None:
    result = CliRunner().invoke(app, ["release", "checklist", "2.6.16"])
    assert result.exit_code == 0
    assert "sac release bump 2.6.16" in result.output
    assert "release preflight" in result.output
