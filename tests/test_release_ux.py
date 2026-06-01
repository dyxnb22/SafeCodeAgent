"""Tests for v2.6.14 release command UX polish."""

from safecode.release.ux import exit_code, header, next_steps, status_label


def test_status_label_is_canonical() -> None:
    assert status_label(True) == "PASS"
    assert status_label(False) == "FAIL"


def test_exit_code_is_canonical() -> None:
    assert exit_code(True) == 0
    assert exit_code(False) == 1


def test_header_includes_title_and_status() -> None:
    lines = header("SafeCode Release Check", True)
    assert lines[0] == "SafeCode Release Check"
    assert "Status: PASS" in lines


def test_next_steps_renders_success_message_when_empty() -> None:
    lines = next_steps([], ok_message="Ready.")
    assert lines == ["Next steps:", "  Ready."]


def test_next_steps_renders_each_step() -> None:
    lines = next_steps(["Fix version.", "Rerun check."])
    assert "  Fix version." in lines
    assert "  Rerun check." in lines
