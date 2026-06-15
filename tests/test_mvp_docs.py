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


def test_v47_debug_docs_cover_workflow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    for text in (readme, guide, troubleshooting):
        assert "sac debug last-failure" in text
        assert "sac debug bundle" in text
    for marker in (
        "sac audit query",
        "Failure Taxonomy (v4.7, EXPERIMENTAL)",
        "EXPERIMENTAL",
    ):
        assert marker in troubleshooting or marker in guide or marker in readme


def test_failure_category_docs_match_code_table() -> None:
    from safecode.core.failure_category import SUGGESTED_COMMAND_BY_CATEGORY

    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    documented: dict[str, str] = {}
    for line in troubleshooting.splitlines():
        if not line.startswith("| `"):
            continue
        columns = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(columns) != 4:
            continue
        category = columns[0].strip("`")
        command = columns[3].strip("`")
        documented[category] = command
    assert documented == SUGGESTED_COMMAND_BY_CATEGORY


def test_documented_v47_debug_and_audit_commands_exist() -> None:
    debug_help = runner.invoke(app, ["debug", "--help"])
    assert debug_help.exit_code == 0
    assert "last-failure" in debug_help.output
    assert "bundle" in debug_help.output

    last_failure_help = runner.invoke(app, ["debug", "last-failure", "--help"])
    assert last_failure_help.exit_code == 0
    assert "--task" in last_failure_help.output
    assert "--json" in last_failure_help.output

    bundle_help = runner.invoke(app, ["debug", "bundle", "--help"])
    assert bundle_help.exit_code == 0
    for option in ("--task", "--out", "--force", "--json"):
        assert option in bundle_help.output

    query_help = runner.invoke(app, ["audit", "query", "--help"])
    assert query_help.exit_code == 0
    for option in ("--type", "--since", "--task", "--limit", "--json"):
        assert option in query_help.output


def test_v419_observability_commands_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "sac task stats" in readme, "README must document sac task stats"
    assert "sac memory size" in readme, "README must document sac memory size"
    assert "v4.19" in readme, "README must reference v4.19"


def test_v419_mvp_guide_inspecting_local_state_section() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    assert "Inspecting Local State" in guide, "MVP guide must have 'Inspecting Local State' section"
    assert "sac task stats" in guide
    assert "sac memory size" in guide
    assert "read-only" in guide.lower()


def test_v419_matrix_has_v419_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.19.0" in matrix
    assert "v4.19.1" in matrix
    assert "v4.19.2" in matrix


def test_v419_commands_exist_on_typer_apps() -> None:
    task_help = runner.invoke(app, ["task", "--help"])
    assert task_help.exit_code == 0
    assert "stats" in task_help.output

    memory_help = runner.invoke(app, ["memory", "--help"])
    assert memory_help.exit_code == 0
    assert "size" in memory_help.output


def test_v420_native_tools_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "v4.20" in readme, "README must reference v4.20"
    assert "read_file" in readme or "native tool" in readme.lower(), "README must mention native tools"


def test_v420_mvp_guide_native_tools_section() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    assert "Native Tools" in guide or "native tool" in guide.lower()
    assert "read_file" in guide
    assert "list_files" in guide
    assert "search_files" in guide
    assert "grep_files" in guide


def test_v420_matrix_has_v420_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.20.0" in matrix
    assert "v4.20.1" in matrix
    assert "v4.20.2" in matrix


def test_v421_write_tools_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "v4.21" in readme
    assert "edit_file" in readme or "write_file" in readme


def test_v421_mvp_guide_making_edits_section() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    assert "edit_file" in guide
    assert "write_file" in guide
    assert "run_command" in guide


def test_v421_matrix_has_v421_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.21.0" in matrix
    assert "v4.21.1" in matrix
    assert "v4.21.2" in matrix


def test_v422_multi_tool_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "v4.22" in readme
    assert "/undo" in readme or "multi-tool" in readme.lower()


def test_v422_mvp_guide_one_turn_section() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    assert "One Turn" in guide or "one turn" in guide.lower()
    assert "/undo" in guide
    assert "/history" in guide
    assert "/tools" in guide


def test_v422_matrix_has_v422_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.22.0" in matrix
    assert "v4.22.1" in matrix
    assert "v4.22.2" in matrix


def test_v423_anthropic_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "v4.23" in readme
    assert "anthropic" in readme.lower()


def test_v423_mvp_guide_first_run_with_claude() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    assert "First-Run with Claude" in guide or "First-run with Claude" in guide
    assert "ANTHROPIC_API_KEY" in guide


def test_v423_matrix_has_v423_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.23.0" in matrix
    assert "v4.23.1" in matrix
    assert "v4.23.2" in matrix


def test_v424_github_tools_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "v4.24" in readme
    assert "github" in readme.lower()


def test_v424_mvp_guide_pr_section() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")
    assert "Open PR" in guide or "open PR" in guide.lower() or "local edits" in guide.lower()
    assert "github_create_pr" in guide


def test_v424_matrix_has_v424_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.24.0" in matrix
    assert "v4.24.1" in matrix
    assert "v4.24.2" in matrix


def test_v425_troubleshooting_has_hardening_sections() -> None:
    trouble = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    assert "CheckpointIntegrityError" in trouble or "checkpoint integrity" in trouble.lower()
    assert "sac_dir_writable" in trouble or ".sac/" in trouble


def test_v425_matrix_has_v425_rows() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v4.25.0" in matrix
    assert "v4.25.1" in matrix
    assert "v4.25.2" in matrix


def test_v500_public_contracts_has_v5_section() -> None:
    contracts = (ROOT / "docs" / "public-contracts.md").read_text(encoding="utf-8")
    assert "v5.0.0 Stable Contract Promotions" in contracts
    assert "sac shell" in contracts.lower() or "sac_shell_loop" in contracts or "shell loop" in contracts.lower()


def test_v500_versioning_policy_has_v5_entry() -> None:
    policy = (ROOT / "docs" / "versioning-policy.md").read_text(encoding="utf-8")
    assert "v5.0.0" in policy
    assert "v5.x" in policy


def test_v500_matrix_has_v500_row() -> None:
    matrix = (ROOT / "docs" / "version_implementation_matrix.md").read_text(encoding="utf-8")
    assert "v5.0.0" in matrix
