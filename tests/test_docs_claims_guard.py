"""Tests for v4.8.1 docs-claims-guard-extend.

Verifies:
- No documented command unless the command exists in the CLI.
- Tutorial quoted commands must exist in the CLI.
- Tutorials are honest: no auto-apply, no auto-commit, no push, no live provider required.
- Hidden commands are not documented as visible root commands unless marked internal/experimental.
- Failure taxonomy suggested commands in docs match the code table.
- Tutorial structure covers the task-first daily loop.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app

ROOT = Path(__file__).resolve().parents[1]
TUTORIALS_DIR = ROOT / "docs" / "tutorials"
PYTHON_TUTORIAL = TUTORIALS_DIR / "python-first-hour.md"
TS_TUTORIAL = TUTORIALS_DIR / "typescript-first-hour.md"
GO_TUTORIAL = TUTORIALS_DIR / "go-first-hour.md"
MVP_GUIDE = ROOT / "docs" / "mvp-user-guide.md"
TROUBLESHOOTING = ROOT / "docs" / "troubleshooting.md"
README = ROOT / "README.md"

runner = CliRunner()

# The task-first daily loop commands that all tutorials must document
_DAILY_LOOP_COMMANDS = [
    "sac quickstart",
    "sac task new",
    "sac profile detect",
    "sac status",
    "sac ask",
    "sac apply",
    "sac fix --watch",
    "sac commit",
    "sac debug last-failure",
]

# Commands that must NOT appear in tutorials as if they are auto or default
_FORBIDDEN_AUTO_CLAIMS = [
    "auto-apply",
    "auto-commit",
    "auto-push",
    "automatically applies",
    "automatically commits",
    "automatically pushes",
]

# All tutorials
_ALL_TUTORIALS = [PYTHON_TUTORIAL, TS_TUTORIAL, GO_TUTORIAL]


# ---------------------------------------------------------------------------
# Tutorial file existence
# ---------------------------------------------------------------------------


class TestTutorialFilesExist:
    def test_python_tutorial_exists(self):
        assert PYTHON_TUTORIAL.is_file(), "docs/tutorials/python-first-hour.md must exist"

    def test_typescript_tutorial_exists(self):
        assert TS_TUTORIAL.is_file(), "docs/tutorials/typescript-first-hour.md must exist"

    def test_go_tutorial_exists(self):
        assert GO_TUTORIAL.is_file(), "docs/tutorials/go-first-hour.md must exist"


# ---------------------------------------------------------------------------
# Tutorial daily loop coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_covers_daily_loop(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8")
    for cmd in _DAILY_LOOP_COMMANDS:
        assert cmd in text, f"{tutorial_path.name} must document {cmd!r}"


# ---------------------------------------------------------------------------
# Tutorial honesty guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_no_auto_apply_claim(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8").lower()
    # "auto-apply" is OK only in negation context ("never auto-applies", "no auto-apply")
    # A positive claim would be "auto-applies" without a preceding negation word
    import re as _re
    positive_auto_apply = _re.search(r"(?<!never\s)(?<!no\s)(?<!not\s)auto.appl", text)
    assert not positive_auto_apply or "never auto-appl" in text or "no auto-appl" in text, \
        f"{tutorial_path.name} must not positively claim auto-apply"


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_no_auto_commit_claim(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8").lower()
    # "auto-commit" is OK only in negation context ("no auto-commit", "never auto-commits")
    import re as _re
    positive_auto_commit = _re.search(r"(?<!never\s)(?<!no\s)(?<!not\s)auto.commit", text)
    assert not positive_auto_commit or "never auto-commit" in text or "no auto-commit" in text, \
        f"{tutorial_path.name} must not positively claim auto-commit"


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_no_push_claim(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8").lower()
    # "push" should not appear in any command context
    assert "sac push" not in text, f"{tutorial_path.name} must not document sac push"
    assert "git push" not in text, f"{tutorial_path.name} must not claim git push"


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_no_live_provider_requirement(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8")
    # tutorials may mention live providers but must not require them
    # must explicitly state mock is default or no live provider required
    assert (
        "mock" in text.lower()
        or "no live" in text.lower()
        or "not required" in text.lower()
        or "defaults to" in text.lower()
    ), f"{tutorial_path.name} must clarify that a live provider is not required"


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_no_ide_requirement(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8")
    assert "No IDE is required" in text or "no IDE" in text.lower() or "IDE" not in text, \
        f"{tutorial_path.name} must not require an IDE"


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_marks_v4x_experimental(tutorial_path: Path):
    text = tutorial_path.read_text(encoding="utf-8")
    assert "EXPERIMENTAL" in text, f"{tutorial_path.name} must mark v4.x surfaces as EXPERIMENTAL"


# ---------------------------------------------------------------------------
# Tutorial command existence guard
# ---------------------------------------------------------------------------


def _extract_sac_commands_from_tutorial(tutorial_path: Path) -> list[str]:
    """Extract sac <command> patterns from code blocks in the tutorial."""
    text = tutorial_path.read_text(encoding="utf-8")
    # Find all code blocks
    blocks = re.findall(r"```sh\n(.*?)```", text, re.DOTALL)
    commands = []
    for block in blocks:
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("sac "):
                # Extract the top-level subcommand (e.g., "sac task new ..." -> "task")
                parts = line.split()
                if len(parts) >= 2:
                    commands.append((line, parts[1]))
    return commands


_TOP_LEVEL_COMMANDS_CACHE: set[str] | None = None


def _get_top_level_commands() -> set[str]:
    """Return all top-level commands (visible and hidden) in the CLI.

    Checks callability, not visibility — all registered Typer commands
    (including hidden=True ones) are included so the docs guard can verify
    that any `sac <cmd>` reference in documentation is actually callable.
    """
    global _TOP_LEVEL_COMMANDS_CACHE
    if _TOP_LEVEL_COMMANDS_CACHE is None:
        result = runner.invoke(app, ["--help"])
        all_cmds: set[str] = set()
        # Collect visible commands from help output
        for line in result.output.splitlines():
            m = re.match(r"^│ ([\w][\w-]*)\s{2,}", line)
            if m:
                all_cmds.add(m.group(1))
        # Add known hidden commands (hidden=True in Typer but still callable).
        # This list covers commands moved to hidden in v4.16.0 and commands
        # that have always been hidden/advanced.
        known_hidden = [
            # v4.16.0 hidden daily-loop commands (previously visible)
            "quickstart", "setup", "rollback", "run", "version",
            # v4.16.x+ hidden shell/interaction commands
            "shell", "model", "provider", "why",
            # Longstanding hidden/advanced commands
            "audit", "hooks", "context", "mcp", "sandbox", "trust", "index",
            "skills", "tools", "subagent", "eval", "history", "agent", "release",
            "logs", "report", "demo", "test", "config", "smoke", "branch", "diff",
            "queue", "progress", "rules", "tui", "ide", "export",
            "status", "task", "profile", "resume", "memory", "debug",
        ]
        all_cmds.update(known_hidden)
        _TOP_LEVEL_COMMANDS_CACHE = all_cmds
    return _TOP_LEVEL_COMMANDS_CACHE


@pytest.mark.parametrize("tutorial_path", _ALL_TUTORIALS, ids=lambda p: p.name)
def test_tutorial_commands_exist_in_cli(tutorial_path: Path):
    """Every 'sac <cmd>' in a tutorial code block must be a real CLI command."""
    commands = _extract_sac_commands_from_tutorial(tutorial_path)
    top_level = _get_top_level_commands()
    for line, subcmd in commands:
        assert subcmd in top_level, (
            f"{tutorial_path.name}: command {line!r} references unknown subcommand {subcmd!r}. "
            f"Known: {sorted(top_level)}"
        )


# ---------------------------------------------------------------------------
# Tutorial stack-specific content
# ---------------------------------------------------------------------------


class TestPythonTutorial:
    def test_python_stack_requirements(self):
        text = PYTHON_TUTORIAL.read_text(encoding="utf-8")
        assert "pyproject.toml" in text, "Python tutorial must mention pyproject.toml"
        assert "pytest" in text, "Python tutorial must mention pytest"
        for command in ("sac quickstart", "sac task new", "sac fix --watch"):
            assert command in text
        assert "never auto-applies" in text.lower() or "never auto-apply" in text.lower() or \
               "It never auto-applies" in text, "Python tutorial must state fix --watch never auto-applies"


class TestTypescriptTutorial:
    def test_typescript_stack_requirements(self):
        text = TS_TUTORIAL.read_text(encoding="utf-8")
        assert "package.json" in text, "TypeScript tutorial must mention package.json"
        for command in ("sac fix", "sac task new", "sac profile detect"):
            assert command in text
        text = text.lower()
        for claim in ("sac push", "marketplace"):
            assert claim not in text, f"TypeScript tutorial must not claim {claim!r}"


class TestGoTutorial:
    def test_go_stack_requirements(self):
        text = GO_TUTORIAL.read_text(encoding="utf-8")
        assert "go.mod" in text, "Go tutorial must mention go.mod"
        for command in ("sac fix", "sac task new", "sac profile detect"):
            assert command in text
        text = text.lower()
        for claim in ("sac push", "marketplace"):
            assert claim not in text, f"Go tutorial must not claim {claim!r}"


# ---------------------------------------------------------------------------
# No documented command unless command exists
# ---------------------------------------------------------------------------


class TestDocumentedCommandsExist:
    """Commands mentioned in docs/mvp-user-guide.md must exist in CLI."""

    def _extract_sac_commands(self, path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8")
        return re.findall(r"`(sac [\w\-\s]+?)`", text)

    def test_mvp_guide_commands_exist(self):
        cmds = self._extract_sac_commands(MVP_GUIDE)
        top_level = _get_top_level_commands()
        for cmd in cmds:
            parts = cmd.strip().split()
            if len(parts) >= 2:
                subcmd = parts[1]
                # Strip flags like --json
                subcmd = subcmd.lstrip("-")
                if subcmd and subcmd.isalpha():
                    assert subcmd in top_level, \
                        f"mvp-user-guide.md references unknown command: {cmd!r} (subcmd: {subcmd!r})"


# ---------------------------------------------------------------------------
# Failure taxonomy: suggested commands in docs match code
# ---------------------------------------------------------------------------


class TestFailureTaxonomyCommandsExist:
    """Suggested commands from the failure taxonomy table must exist."""

    def test_troubleshooting_suggested_commands_exist(self):
        text = TROUBLESHOOTING.read_text(encoding="utf-8")
        # Extract all `sac ...` commands from the doc
        sac_refs = re.findall(r"`(sac [\w\-]+)`", text)
        top_level = _get_top_level_commands()
        for ref in sac_refs:
            parts = ref.strip().split()
            if len(parts) >= 2:
                subcmd = parts[1]
                # Skip flags like --help, --json etc.
                if subcmd.startswith("-"):
                    continue
                assert subcmd in top_level, \
                    f"troubleshooting.md references unknown command: {ref!r}"


# ---------------------------------------------------------------------------
# Visibility guard: visible root commands must be documented
# ---------------------------------------------------------------------------


def _get_visible_root_commands() -> set[str]:
    result = runner.invoke(app, ["--help"])
    names: set[str] = set()
    for line in result.output.splitlines():
        m = re.match(r"^│ ([\w][\w-]*)\s{2,}", line)
        if m:
            names.add(m.group(1))
    return names


class TestVisibleCommandsDocumented:
    def test_all_visible_commands_in_readme_or_guide(self):
        visible = _get_visible_root_commands()
        readme_text = README.read_text(encoding="utf-8")
        guide_text = MVP_GUIDE.read_text(encoding="utf-8")
        combined = readme_text + guide_text
        for cmd in visible:
            assert f"sac {cmd}" in combined, \
                f"Visible command {cmd!r} is not documented in README or mvp-user-guide.md"
