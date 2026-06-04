"""Tests for v2.7.6 cli-help-surface-trim.

Verifies that:
- Advanced/internal commands are hidden from sac --help.
- Hidden commands remain directly callable.
- Core new-user commands appear in sac --help.
"""

from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()

_HIDDEN_COMMANDS = ["queue", "progress", "rules", "tui", "ide", "export"]
_CORE_COMMANDS = ["setup", "quickstart", "ask", "edit", "apply", "rollback", "run", "doctor", "version"]


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


class TestCoreCommandsVisibleInRootHelp:
    def test_quickstart_visible(self):
        assert "quickstart" in _command_names_in_root_help()

    def test_setup_visible(self):
        assert "setup" in _command_names_in_root_help()

    def test_ask_visible(self):
        assert "ask" in _command_names_in_root_help()

    def test_edit_visible(self):
        assert "edit" in _command_names_in_root_help()

    def test_apply_visible(self):
        assert "apply" in _command_names_in_root_help()

    def test_rollback_visible(self):
        assert "rollback" in _command_names_in_root_help()

    def test_run_visible(self):
        assert "run" in _command_names_in_root_help()

    def test_doctor_visible(self):
        assert "doctor" in _command_names_in_root_help()

    def test_version_visible(self):
        assert "version" in _command_names_in_root_help()
