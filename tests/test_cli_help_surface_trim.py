"""Tests for CLI help surface contracts.

v2.7.6: Advanced/internal commands hidden; hidden commands callable; core commands visible.
v4.16.0: Root help trimmed to 7 daily-loop commands. Previously visible commands moved to
         hidden-but-callable. The safety primitive `rollback` is reachable via `sac help --all`.
"""

from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()

# v4.16+ visible daily-loop set (exactly these 7 appear in `sac --help`)
_V416_VISIBLE_COMMANDS = {"init", "ask", "edit", "apply", "fix", "commit", "doctor"}

# Commands that were visible before v4.16.0, now hidden-but-callable
_NOW_HIDDEN_BUT_CALLABLE = ["quickstart", "setup", "rollback", "run", "version", "shell"]

_HIDDEN_COMMANDS = ["queue", "progress", "rules", "tui", "ide", "export"]


def _command_names_in_root_help() -> set[str]:
    """Return the set of command names listed in sac --help (first word of each command row)."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    names: set[str] = set()
    in_commands = False
    for line in result.output.splitlines():
        if "Commands" in line:
            in_commands = True
            continue
        if in_commands:
            stripped = line.strip().lstrip("│").strip()
            if stripped and not stripped.startswith("─") and not stripped.startswith("╰"):
                first = stripped.split()[0] if stripped.split() else ""
                if first:
                    names.add(first)
    return names


class TestHiddenCommandsNotInRootHelp:
    def test_queue_hidden_from_root_help(self):
        assert "queue" not in _command_names_in_root_help()

    def test_progress_hidden_from_root_help(self):
        assert "progress" not in _command_names_in_root_help()

    def test_rules_hidden_from_root_help(self):
        assert "rules" not in _command_names_in_root_help()

    def test_tui_hidden_from_root_help(self):
        assert "tui" not in _command_names_in_root_help()

    def test_ide_hidden_from_root_help(self):
        assert "ide" not in _command_names_in_root_help()

    def test_export_hidden_from_root_help(self):
        assert "export" not in _command_names_in_root_help()


class TestHiddenCommandsStillCallable:
    def test_queue_help_accessible(self):
        result = runner.invoke(app, ["queue", "--help"])
        assert result.exit_code == 0

    def test_memory_help_accessible(self):
        result = runner.invoke(app, ["memory", "--help"])
        assert result.exit_code == 0

    def test_progress_help_accessible(self):
        result = runner.invoke(app, ["progress", "--help"])
        assert result.exit_code == 0

    def test_rules_help_accessible(self):
        result = runner.invoke(app, ["rules", "--help"])
        assert result.exit_code == 0

    def test_tui_help_accessible(self):
        result = runner.invoke(app, ["tui", "--help"])
        assert result.exit_code == 0

    def test_ide_help_accessible(self):
        result = runner.invoke(app, ["ide", "--help"])
        assert result.exit_code == 0

    def test_export_help_accessible(self):
        result = runner.invoke(app, ["export", "--help"])
        assert result.exit_code == 0


class TestV416CoreCommandsVisibleInRootHelp:
    """v4.16+ root help shows exactly the 7-command daily-loop set."""

    def test_init_visible(self):
        assert "init" in _command_names_in_root_help()

    def test_ask_visible(self):
        assert "ask" in _command_names_in_root_help()

    def test_edit_visible(self):
        assert "edit" in _command_names_in_root_help()

    def test_apply_visible(self):
        assert "apply" in _command_names_in_root_help()

    def test_fix_visible(self):
        assert "fix" in _command_names_in_root_help()

    def test_commit_visible(self):
        assert "commit" in _command_names_in_root_help()

    def test_doctor_visible(self):
        assert "doctor" in _command_names_in_root_help()


class TestPreviouslyVisibleCommandsStillCallable:
    """Commands removed from root help in v4.16.0 remain callable."""

    def test_quickstart_help_accessible(self):
        result = runner.invoke(app, ["quickstart", "--help"])
        assert result.exit_code == 0

    def test_setup_help_accessible(self):
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0

    def test_rollback_help_accessible(self):
        result = runner.invoke(app, ["rollback", "--help"])
        assert result.exit_code == 0

    def test_run_help_accessible(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0

    def test_version_help_accessible(self):
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0

    def test_shell_help_accessible(self):
        result = runner.invoke(app, ["shell", "--help"])
        assert result.exit_code == 0
