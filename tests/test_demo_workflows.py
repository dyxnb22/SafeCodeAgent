"""Demo workflow suite tests for v2.0.4."""

from pathlib import Path

from typer.testing import CliRunner

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.cli import app
from safecode.demo.workflows import DemoWorkflowSuite
from safecode.project.test_detector import ProjectTestDetector

runner = CliRunner()


def test_default_suite_covers_onboarding_demo_workflow_categories() -> None:
    workflows = DemoWorkflowSuite().list()

    assert [workflow.category for workflow in workflows] == ["fastapi", "cli", "docs", "failing-test", "safe-shell"]
    assert [workflow.id for workflow in workflows] == [
        "fastapi-health-endpoint",
        "cli-version-flag",
        "docs-safety-note",
        "failing-test-repair",
        "safe-shell-status",
    ]


def test_materialize_writes_seed_project_and_refuses_overwrite(tmp_path: Path) -> None:
    suite = DemoWorkflowSuite()

    project_root = suite.materialize("failing-test-repair", tmp_path)

    assert (project_root / "src" / "calculator.py").exists()
    assert (project_root / "tests" / "test_calculator.py").exists()
    assert "left - right" in (project_root / "src" / "calculator.py").read_text(encoding="utf-8")

    try:
        suite.materialize("failing-test-repair", tmp_path)
    except FileExistsError as exc:
        assert "failing-test-repair" in str(exc)
    else:
        raise AssertionError("materialize should refuse to overwrite an existing demo")


def test_test_detector_finds_pytest_for_runnable_demo_workflows(tmp_path: Path) -> None:
    suite = DemoWorkflowSuite()

    for workflow_id in ("fastapi-health-endpoint", "cli-version-flag", "failing-test-repair"):
        project_root = suite.materialize(workflow_id, tmp_path)
        commands = [candidate.command for candidate in ProjectTestDetector(project_root).detect()]

        assert "pytest -q" in commands


def test_mock_patch_responses_cover_all_editable_demo_workflows(tmp_path: Path) -> None:
    suite = DemoWorkflowSuite()
    expectations = {
        "fastapi-health-endpoint": ("app/main.py", '@app.get("/health")'),
        "cli-version-flag": ("src/todo_cli/cli.py", "--version"),
        "docs-safety-note": ("docs/usage.md", "checkpoint prompt"),
        "failing-test-repair": ("src/calculator.py", "left + right"),
    }

    for workflow_id, (expected_file, expected_text) in expectations.items():
        project_root = suite.materialize(workflow_id, tmp_path)
        workflow = suite.get(workflow_id)

        result = AgentOrchestrator(project_root).edit(workflow.task)

        assert result.proposal.blocks[0].file_path.as_posix() == expected_file
        assert expected_text in result.diff_text


def test_cli_demo_commands_list_show_and_materialize(tmp_path: Path) -> None:
    list_result = runner.invoke(app, ["demo", "list"])
    show_result = runner.invoke(app, ["demo", "show", "cli-version-flag"])
    materialize_result = runner.invoke(
        app,
        ["demo", "materialize", "docs-safety-note", "--destination", str(tmp_path)],
    )

    assert list_result.exit_code == 0
    assert "fastapi-health-endpoint" in list_result.stdout
    assert show_result.exit_code == 0
    assert "Add a --version flag" in show_result.stdout
    assert materialize_result.exit_code == 0
    assert (tmp_path / "docs-safety-note" / "docs" / "usage.md").exists()
