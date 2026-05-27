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


def test_rollback_last_restores_applied_patch(tmp_path) -> None:
    readme = tmp_path / "README.md"
    original_text = (
        "# Demo\n\n"
        "This repository currently contains the project framework only. "
        "The implementation should be added step by step after reviewing each module boundary.\n"
    )
    readme.write_text(original_text, encoding="utf-8")

    orchestrator = AgentOrchestrator(tmp_path)
    orchestrator.edit("演示一次安全修改")
    preview = orchestrator.preview_apply()
    orchestrator.apply(preview.proposal)

    rollback = orchestrator.rollback_last()
    history = orchestrator.history()

    assert rollback.files == ["README.md"]
    assert readme.read_text(encoding="utf-8") == original_text
    assert history[-1].type == "rollback_completed"


def test_fastapi_demo_patch_is_selected_when_app_main_exists(tmp_path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    main_file = app_dir / "main.py"
    main_file.write_text(
        '''"""Minimal FastAPI demo target for SafeCode Agent."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root() -> dict[str, str]:
    """Return a tiny demo response."""
    return {"message": "hello from fastapi demo"}
''',
        encoding="utf-8",
    )

    result = AgentOrchestrator(tmp_path).edit("给这个 FastAPI 项目添加 /health 接口")

    assert result.proposal.blocks[0].file_path.as_posix() == "app/main.py"
    assert '@app.get("/health")' in result.diff_text
