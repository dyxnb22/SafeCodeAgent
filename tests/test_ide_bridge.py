from typer.testing import CliRunner

from safecode.cli import app
from safecode.ide.bridge import pending_diff_target, selected_file_targets
from safecode.ide.manifest import render_manifest
from safecode.patch.models import PatchBlock, PatchProposal


def _write_pending_patch(tmp_path):
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    proposal = PatchProposal(
        id="p1",
        task="update readme",
        blocks=[PatchBlock(operation="update", file_path="README.md", search="old\n", replace="new\n")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )
    pending = tmp_path / ".sac" / "pending_patch.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(proposal.model_dump_json(), encoding="utf-8")


def test_manifest_includes_bridge_commands():
    manifest = render_manifest()
    assert "safecode.openDiff" in manifest
    assert "safecode.openSelectedFiles" in manifest


def test_pending_diff_target_materializes_diff(tmp_path):
    _write_pending_patch(tmp_path)
    target = pending_diff_target(tmp_path)
    assert target.path.exists()
    assert target.uri.startswith("file://")
    assert "+new" in target.path.read_text(encoding="utf-8")


def test_selected_file_targets_returns_safe_project_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    targets = selected_file_targets(tmp_path, "hello app", limit=3)
    assert targets
    assert targets[0].uri.startswith("file://")
    assert targets[0].path.name == "app.py"


def test_ide_open_diff_cli(tmp_path, monkeypatch):
    _write_pending_patch(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["ide", "open-diff"])
    assert result.exit_code == 0
    assert "pending.diff" in result.output


def test_ide_open_files_cli(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["ide", "open-files", "hello"])
    assert result.exit_code == 0
    assert "app.py" in result.output
