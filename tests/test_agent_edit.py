"""Tests for the v0.1.2 edit workflow."""

from safecode.agent.orchestrator import AgentOrchestrator


def test_edit_saves_pending_patch_without_modifying_target_file(tmp_path) -> None:
    readme = tmp_path / "README.md"
    original_text = (
        "# Demo\n\n"
        "This repository currently contains the project framework only. "
        "The implementation should be added step by step after reviewing each module boundary.\n"
    )
    readme.write_text(original_text, encoding="utf-8")

    result = AgentOrchestrator(tmp_path).edit("演示一次安全修改")

    assert result.pending_patch_path.exists()
    assert result.proposal.blocks[0].file_path.as_posix() == "README.md"
    assert "--- a/README.md" in result.diff_text
    assert "+This repository currently contains the SafeCode Agent v0.1 framework." in result.diff_text
    assert readme.read_text(encoding="utf-8") == original_text


def test_preview_apply_and_apply_pending_patch(tmp_path) -> None:
    readme = tmp_path / "README.md"
    original_text = (
        "# Demo\n\n"
        "This repository currently contains the project framework only. "
        "The implementation should be added step by step after reviewing each module boundary.\n"
    )
    readme.write_text(original_text, encoding="utf-8")

    orchestrator = AgentOrchestrator(tmp_path)
    edit_result = orchestrator.edit("演示一次安全修改")

    preview = orchestrator.preview_apply()
    apply_result = orchestrator.apply(preview.proposal)

    assert preview.proposal.id == edit_result.proposal.id
    assert apply_result.checkpoint.checkpoint_id
    assert apply_result.files == ["README.md"]
    assert not edit_result.pending_patch_path.exists()
    assert "SafeCode Agent v0.1 framework" in readme.read_text(encoding="utf-8")
