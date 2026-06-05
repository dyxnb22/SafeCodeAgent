"""Tests for v4.8.0 cli-surface-trim (updated v4.9).

Verifies the root help surface:
- At most 19 visible commands (daily-loop set + sac shell + sac model).
- All previously hidden commands remain callable.
- Newly hidden commands are not in root help.
- memory is now visible in root help.
- smoke is hidden but callable.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()

# Target visible set (19 commands after adding sac model)
_TARGET_VISIBLE = frozenset({
    "setup",
    "quickstart",
    "status",
    "task",
    "ask",
    "edit",
    "fix",
    "apply",
    "rollback",
    "run",
    "commit",
    "profile",
    "resume",
    "memory",
    "debug",
    "doctor",
    "version",
    "shell",
    "model",
})

# Commands hidden in v4.8.0 (callable but not in root help)
_HIDDEN_IN_V4_8 = [
    "queue",
    "progress",
    "rules",
    "tui",
    "ide",
    "export",
    "audit",
    "hooks",
    "context",
    "mcp",
    "sandbox",
    "trust",
    "index",
    "skills",
    "tools",
    "subagent",
    "eval",
    "history",
    "agent",
    "release",
    "logs",
    "report",
    "demo",
    "test",
    "config",
    "smoke",
]

# Typer command lines: "│ <name>  <description>" (Unicode box-drawing char U+2502).
# Continuation lines have more leading spaces and are excluded.
_COMMAND_LINE_RE = re.compile(r"^│ ([\w][\w-]*)\s{2,}")


def _command_names_in_root_help() -> set[str]:
    """Return the set of command names from sac --help (command lines only, not continuations)."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    names: set[str] = set()
    for line in result.output.splitlines():
        m = _COMMAND_LINE_RE.match(line)
        if m:
            names.add(m.group(1))
    return names


class TestV48VisibleSurface:
    def test_visible_count_at_most_18(self):
        """sac provider adds one daily-use command group to the root surface (v4.14.0)."""
        names = _command_names_in_root_help()
        assert len(names) <= 20, f"Expected <=20 visible commands, got {len(names)}: {sorted(names)}"

    def test_all_target_commands_visible(self):
        names = _command_names_in_root_help()
        for cmd in _TARGET_VISIBLE:
            assert cmd in names, f"Expected {cmd!r} to be visible in root help"

    def test_memory_now_visible(self):
        assert "memory" in _command_names_in_root_help()

    def test_setup_visible(self):
        assert "setup" in _command_names_in_root_help()

    def test_quickstart_visible(self):
        assert "quickstart" in _command_names_in_root_help()

    def test_status_visible(self):
        assert "status" in _command_names_in_root_help()

    def test_task_visible(self):
        assert "task" in _command_names_in_root_help()

    def test_ask_visible(self):
        assert "ask" in _command_names_in_root_help()

    def test_edit_visible(self):
        assert "edit" in _command_names_in_root_help()

    def test_fix_visible(self):
        assert "fix" in _command_names_in_root_help()

    def test_apply_visible(self):
        assert "apply" in _command_names_in_root_help()

    def test_rollback_visible(self):
        assert "rollback" in _command_names_in_root_help()

    def test_run_visible(self):
        assert "run" in _command_names_in_root_help()

    def test_commit_visible(self):
        assert "commit" in _command_names_in_root_help()

    def test_profile_visible(self):
        assert "profile" in _command_names_in_root_help()

    def test_resume_visible(self):
        assert "resume" in _command_names_in_root_help()

    def test_debug_visible(self):
        assert "debug" in _command_names_in_root_help()

    def test_doctor_visible(self):
        assert "doctor" in _command_names_in_root_help()

    def test_version_visible(self):
        assert "version" in _command_names_in_root_help()


class TestV48HiddenNotInRootHelp:
    def test_audit_hidden(self):
        assert "audit" not in _command_names_in_root_help()

    def test_hooks_hidden(self):
        assert "hooks" not in _command_names_in_root_help()

    def test_context_hidden(self):
        assert "context" not in _command_names_in_root_help()

    def test_mcp_hidden(self):
        assert "mcp" not in _command_names_in_root_help()

    def test_sandbox_hidden(self):
        assert "sandbox" not in _command_names_in_root_help()

    def test_trust_hidden(self):
        assert "trust" not in _command_names_in_root_help()

    def test_index_hidden(self):
        assert "index" not in _command_names_in_root_help()

    def test_skills_hidden(self):
        assert "skills" not in _command_names_in_root_help()

    def test_tools_hidden(self):
        assert "tools" not in _command_names_in_root_help()

    def test_subagent_hidden(self):
        assert "subagent" not in _command_names_in_root_help()

    def test_eval_hidden(self):
        assert "eval" not in _command_names_in_root_help()

    def test_history_hidden(self):
        assert "history" not in _command_names_in_root_help()

    def test_agent_hidden(self):
        assert "agent" not in _command_names_in_root_help()

    def test_release_hidden(self):
        assert "release" not in _command_names_in_root_help()

    def test_logs_hidden(self):
        assert "logs" not in _command_names_in_root_help()

    def test_report_hidden(self):
        assert "report" not in _command_names_in_root_help()

    def test_demo_hidden(self):
        assert "demo" not in _command_names_in_root_help()

    def test_test_hidden(self):
        assert "test" not in _command_names_in_root_help()

    def test_config_hidden(self):
        assert "config" not in _command_names_in_root_help()

    def test_smoke_hidden(self):
        assert "smoke" not in _command_names_in_root_help()

    def test_branch_hidden(self):
        assert "branch" not in _command_names_in_root_help()

    def test_diff_hidden(self):
        assert "diff" not in _command_names_in_root_help()


class TestV48HiddenCommandsStillCallable:
    def test_audit_callable(self):
        result = runner.invoke(app, ["audit", "--help"])
        assert result.exit_code == 0

    def test_hooks_callable(self):
        result = runner.invoke(app, ["hooks", "--help"])
        assert result.exit_code == 0

    def test_context_callable(self):
        result = runner.invoke(app, ["context", "--help"])
        assert result.exit_code == 0

    def test_mcp_callable(self):
        result = runner.invoke(app, ["mcp", "--help"])
        assert result.exit_code == 0

    def test_sandbox_callable(self):
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0

    def test_trust_callable(self):
        result = runner.invoke(app, ["trust", "--help"])
        assert result.exit_code == 0

    def test_index_callable(self):
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0

    def test_skills_callable(self):
        result = runner.invoke(app, ["skills", "--help"])
        assert result.exit_code == 0

    def test_tools_callable(self):
        result = runner.invoke(app, ["tools", "--help"])
        assert result.exit_code == 0

    def test_subagent_callable(self):
        result = runner.invoke(app, ["subagent", "--help"])
        assert result.exit_code == 0

    def test_eval_callable(self):
        result = runner.invoke(app, ["eval", "--help"])
        assert result.exit_code == 0

    def test_history_callable(self):
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0

    def test_agent_callable(self):
        result = runner.invoke(app, ["agent", "--help"])
        assert result.exit_code == 0

    def test_release_callable(self):
        result = runner.invoke(app, ["release", "--help"])
        assert result.exit_code == 0

    def test_logs_callable(self):
        result = runner.invoke(app, ["logs", "--help"])
        assert result.exit_code == 0

    def test_report_callable(self):
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_smoke_callable(self):
        result = runner.invoke(app, ["smoke", "--help"])
        assert result.exit_code == 0

    def test_smoke_shell_first_help_callable(self):
        result = runner.invoke(app, ["smoke", "shell-first", "--help"])
        assert result.exit_code == 0

    def test_config_callable(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_branch_callable(self):
        result = runner.invoke(app, ["branch", "--help"])
        assert result.exit_code == 0

    def test_diff_callable(self):
        result = runner.invoke(app, ["diff", "--help"])
        assert result.exit_code == 0
