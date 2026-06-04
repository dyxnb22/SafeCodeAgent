"""MVP documentation regression tests for v2.0.5."""

from pathlib import Path
from typer.testing import CliRunner

from safecode.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_mvp_user_guide_covers_new_user_path() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")

    required_sections = [
        "## Install",
        "## Model Configuration",
        "## First Task: Failing-Test Repair",
        "## Safety Model",
        "## Rollback",
    ]
    for section in required_sections:
        assert section in guide

    required_commands = [
        "uv sync",
        "uv tool install .",
        "sac demo materialize failing-test-repair",
        "sac test run --yes",
        "sac edit",
        "sac apply",
        "sac rollback --last",
        "sac history",
    ]
    for command in required_commands:
        assert command in guide


def test_model_config_docs_match_current_policy_boundaries() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")

    assert "SafeCode defaults to the deterministic `mock` provider" in guide
    assert "network_enabled = true" in guide
    assert 'network_allowlist = ["api.openai.com"]' in guide
    assert "Both sides are required" in guide
    assert "a project\ncannot enable network access or choose a provider by itself" in guide
    assert "OPENAI_API_KEY" in guide


def test_readme_links_to_mvp_guide_and_first_demo() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/mvp-user-guide.md" in readme
    assert "## First Demo Task" in readme
    assert "sac demo materialize failing-test-repair" in readme
    assert "sac rollback --last" in readme


def test_v43_fix_watch_docs_cover_approval_gated_loop() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")

    for text in (readme, guide):
        assert "sac fix --watch" in text
        assert "--max-iterations" in text
        assert "--timeout-seconds" in text
        assert "--rerun-suite" in text
        assert "never" in text.lower()
        assert "sac apply" in text

    for marker in (
        "loop_no_progress",
        "command_timeout",
        "Max iterations reached",
        "Blocked suite command",
        "Missing profile suite",
    ):
        assert marker in troubleshooting


def test_documented_v43_fix_options_exist() -> None:
    result = runner.invoke(app, ["fix", "--help"])
    assert result.exit_code == 0
    for option in ("--watch", "--max-iterations", "--timeout-seconds", "--rerun-suite"):
        assert option in result.output


def test_v44_resume_budget_docs_cover_recovery_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")

    for text in (readme, guide):
        assert "sac resume" in text
        assert "sac task budget show" in text
        assert "sac task budget set" in text
        assert "EXPERIMENTAL" in text
        assert "never" in text.lower()

    for marker in ("interrupted", "budget_exceeded", "loop_stuck", "closed"):
        assert marker in troubleshooting


def test_documented_v44_commands_exist() -> None:
    resume = runner.invoke(app, ["resume", "--help"])
    assert resume.exit_code == 0
    assert "--json" in resume.output

    budget_show = runner.invoke(app, ["task", "budget", "show", "--help"])
    assert budget_show.exit_code == 0
    assert "--task" in budget_show.output

    budget_set = runner.invoke(app, ["task", "budget", "set", "--help"])
    assert budget_set.exit_code == 0
    for option in ("--steps", "--time-seconds", "--retries", "--tokens"):
        assert option in budget_set.output


def test_v45_local_git_docs_cover_delivery_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")

    for text in (readme, guide):
        assert "sac commit" in text
        assert "sac branch new" in text
        assert "sac diff --task" in text
        assert "dirty-tree guard" in text
        assert "EXPERIMENTAL" in text

    for marker in (
        "Dirty unrelated changes",
        "Rollback after committed apply",
        "Branch creation refusal",
        "Unknown task files",
    ):
        assert marker in troubleshooting


def test_documented_v45_commands_exist() -> None:
    commit = runner.invoke(app, ["commit", "--help"])
    assert commit.exit_code == 0
    for option in ("--message-from-task", "--branch", "--include-task-summary", "--json"):
        assert option in commit.output

    branch = runner.invoke(app, ["branch", "new", "--help"])
    assert branch.exit_code == 0
    assert "--json" in branch.output

    diff = runner.invoke(app, ["diff", "--help"])
    assert diff.exit_code == 0
    assert "--task" in diff.output


def test_v46_memory_docs_cover_unified_memory_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")

    for text in (readme, guide):
        for command in (
            "sac memory show",
            "sac memory pin",
            "sac memory unpin",
            "sac memory add-note",
            "sac memory clear",
        ):
            assert command in text
        assert ".sac/memory/project.md" in text
        assert ".sac/tasks/<task_id>/memory.md" in text
        assert "recent failures" in text.lower()
        assert "EXPERIMENTAL" in text

    for marker in (
        "Pinned file missing",
        "Pinned file outside project root",
        "Memory secret rejection",
        "Recent failure context too stale",
    ):
        assert marker in troubleshooting


def test_documented_v46_memory_commands_exist() -> None:
    memory_help = runner.invoke(app, ["memory", "--help"])
    assert memory_help.exit_code == 0
    for command in ("show", "pin", "unpin", "add-note", "clear"):
        assert command in memory_help.output

    show_help = runner.invoke(app, ["memory", "show", "--help"])
    assert show_help.exit_code == 0
    for option in ("--project", "--task", "--recent-failures", "--recent-edits", "--pinned", "--json"):
        assert option in show_help.output

    clear_help = runner.invoke(app, ["memory", "clear", "--help"])
    assert clear_help.exit_code == 0
    assert "--yes" in clear_help.output
