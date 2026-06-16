from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
TUTORIAL = ROOT / "docs" / "tutorials" / "from-task-to-tested-commit.md"
AGENT_TUTORIAL = ROOT / "docs" / "tutorials" / "agent-run-first-hour.md"
EXAMPLE = ROOT / "examples" / "fastapi-todo"
TRANSCRIPT = EXAMPLE / "demo" / "expected-transcript.md"
RUN_DEMO = EXAMPLE / "demo" / "run-demo.sh"
PUBLIC_CONTRACTS = ROOT / "docs" / "public-contracts.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_DEMO_HEADING = "## Reproducible demo: from bug report to tested commit"
_INSTALL_HEADING = "## Install"


def _readme_demo_section() -> str:
    text = _text(README)
    start = text.index(_DEMO_HEADING)
    end = text.index(_INSTALL_HEADING)
    return text[start:end]


def test_readme_has_front_door_demo_section_near_top() -> None:
    text = _text(README)

    assert _DEMO_HEADING in text
    assert text.index(_DEMO_HEADING) < text.index(_INSTALL_HEADING)


def test_readme_demo_section_is_concise_and_practical() -> None:
    section = _readme_demo_section()
    command_lines = [
        line
        for line in section.splitlines()
        if line.startswith(("uv ", "cd ", "git ", "examples/", "sac "))
    ]

    assert len(command_lines) <= 6


def test_readme_references_example_transcript_and_tutorial() -> None:
    section = _readme_demo_section()

    # v5.6.0: points to golden-demo (files created in v5.6.2)
    assert "golden-demo" in section
    assert "expected-transcript.md" in section
    assert "portfolio-demo.md" in section


def test_tutorial_and_agent_first_hour_exist() -> None:
    assert TUTORIAL.is_file()
    assert AGENT_TUTORIAL.is_file()


def test_tutorial_lists_commands_used_by_run_demo_and_transcript() -> None:
    tutorial = _text(TUTORIAL) + "\n" + _text(AGENT_TUTORIAL)
    run_demo = _text(RUN_DEMO)
    transcript = _text(TRANSCRIPT)
    expected_fragments = [
        "uv sync --extra examples",
        "cd examples/fastapi-todo",
        "pytest -q",
        "sac demo agent-loop",
        "PYTHONPATH=src pytest -q",
    ]

    for fragment in expected_fragments:
        assert fragment in tutorial
    assert "sac demo agent-loop" in run_demo
    assert "$ PYTHONPATH=src pytest -q" in transcript


def test_demo_docs_do_not_claim_forbidden_automation_or_requirements() -> None:
    combined = "\n".join(_text(path).lower() for path in [README, TUTORIAL, AGENT_TUTORIAL])

    forbidden_positive = [
        "automatically applies",
        "automatically commits",
        "requires a live provider",
        "requires an ide",
        "git push",
        "sac push",
        "pull request automation",
    ]
    for phrase in forbidden_positive:
        assert phrase not in combined

    assert "no auto-apply" in combined
    assert "no auto-commit" in combined
    assert "no live provider" in combined
    assert "no ide is required" in combined


def test_public_contracts_keep_v410_v412_experimental() -> None:
    text = _text(PUBLIC_CONTRACTS)
    section = text[text.index("## v4.10-v4.12 Resume-MVP Contract Summary") : text.index("## Stable Contracts")]

    assert "zero new stable contracts" in section
    assert "EXPERIMENTAL" in section
    assert "No v4.10-v4.12 surface is a stable contract" in section


def test_expected_transcript_uses_stable_annotations() -> None:
    text = _text(TRANSCRIPT)

    assert "<temp-worktree>" in text
    assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:\d\d", text)
    assert "review boundary" in text
    assert "commit prompt" in text
