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


def test_tutorial_docs_exist():
    docs = Path("docs/tutorials")
    for name in ["bug-fix.md", "feature-edit.md", "docs-edit.md", "safe-shell-task.md"]:
        path = docs / name
        assert path.exists()
        assert "sac " in path.read_text(encoding="utf-8")
