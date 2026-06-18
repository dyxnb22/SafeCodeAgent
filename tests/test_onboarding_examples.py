from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.demo.workflows import DemoWorkflowSuite


def test_onboarding_workflows_cover_four_paths():
    workflows = {workflow.id: workflow for workflow in DemoWorkflowSuite().list()}
    assert "failing-test-repair" in workflows
    assert "fastapi-health-endpoint" in workflows
    assert "docs-safety-note" in workflows
    assert "safe-shell-status" in workflows
    assert workflows["safe-shell-status"].category == "safe-shell"


def test_safe_shell_workflow_materializes(tmp_path):
    root = DemoWorkflowSuite().materialize("safe-shell-status", tmp_path)
    assert (root / "README.md").exists()
    assert (root / ".sac" / "config.toml").exists()
    assert "git" in (root / ".sac" / "config.toml").read_text(encoding="utf-8")


def test_demo_list_shows_safe_shell_workflow():
    result = CliRunner().invoke(app, ["demo", "list"])
    assert result.exit_code == 0
    assert "safe-shell-status" in result.output


def test_tutorial_index_covers_focused_workflows():
    text = Path("docs/tutorials/README.md").read_text(encoding="utf-8")
    for workflow in [
        "failing-test-repair",
        "fastapi-health-endpoint",
        "docs-safety-note",
        "safe-shell-status",
    ]:
        assert workflow in text
    assert "sac edit" in text
    assert "sac run" in text
