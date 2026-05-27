"""Tests for applying patch proposals."""

from pathlib import Path

import pytest

from safecode.patch.applier import PatchApplier
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.patch.validator import PatchValidationError


def make_proposal(search: str, replace: str, file_path: str = "README.md") -> PatchProposal:
    return PatchProposal(
        id="patch_apply",
        task="apply test",
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


def test_apply_updates_file_once(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("hello world\n", encoding="utf-8")
    proposal = make_proposal("hello world", "hello safecode")

    PatchApplier(tmp_path).apply(proposal)

    assert readme.read_text(encoding="utf-8") == "hello safecode\n"


def test_apply_rejects_non_unique_search(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("hello\nhello\n", encoding="utf-8")
    proposal = make_proposal("hello", "hi")

    with pytest.raises(PatchValidationError, match="exactly once"):
        PatchApplier(tmp_path).apply(proposal)

    assert readme.read_text(encoding="utf-8") == "hello\nhello\n"
