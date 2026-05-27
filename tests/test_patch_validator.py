"""Tests for patch validation rules."""

from pathlib import Path

import pytest

from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.patch.validator import PatchValidationError, PatchValidator


def make_proposal(search: str, replace: str, file_path: str = "README.md") -> PatchProposal:
    return PatchProposal(
        id="patch_test",
        task="test patch",
        blocks=[
            PatchBlock(
                operation="update",
                file_path=Path(file_path),
                search=search,
                replace=replace,
            )
        ],
        created_at="2026-05-21T12:30:00Z",
        model="mock",
    )


def test_validate_accepts_unique_search(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("hello world\n", encoding="utf-8")
    proposal = make_proposal("hello world", "hello safecode")

    PatchValidator(tmp_path).validate(proposal)


def test_validate_rejects_missing_file(tmp_path) -> None:
    proposal = make_proposal("hello", "hi")

    with pytest.raises(PatchValidationError, match="does not exist"):
        PatchValidator(tmp_path).validate(proposal)


def test_validate_rejects_duplicate_search(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("hello\nhello\n", encoding="utf-8")
    proposal = make_proposal("hello", "hi")

    with pytest.raises(PatchValidationError, match="matched 2 times"):
        PatchValidator(tmp_path).validate(proposal)


def test_validate_rejects_path_escape(tmp_path) -> None:
    proposal = make_proposal("secret", "safe", "../secret.txt")

    with pytest.raises(PatchValidationError, match="escapes project root"):
        PatchValidator(tmp_path).validate(proposal)


def test_build_unified_diff_does_not_modify_file(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("hello world\n", encoding="utf-8")
    proposal = make_proposal("hello world", "hello safecode")

    diff_text = build_unified_diff(tmp_path, proposal)

    assert "--- a/README.md" in diff_text
    assert "+++ b/README.md" in diff_text
    assert "-hello world" in diff_text
    assert "+hello safecode" in diff_text
    assert readme.read_text(encoding="utf-8") == "hello world\n"
